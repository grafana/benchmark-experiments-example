// Offline eval of the o11y-bench tasks with k6, optionally reported to Agent
// Observability as an experiment (Experiments > Experiment runs).
//
// Each trial is one fresh o11y-bench Harbor job (the agent, its isolated Docker
// stack and the benchmark's own verifier), run by k6_evals.py's runner. The trial
// passes when the verifier's reward is 1.0, the benchmark's full-pass criterion.
//
//   EXPERIMENT_PUBLISH=false (default)  run and score locally; no Cloud calls
//   EXPERIMENT_PUBLISH=true             also create the experiment in Grafana Cloud,
//                                       record each trial's conversation and score
//
// Run it with `make k6-evals`, which serves the runner around this script.
import http from 'k6/http';
import { Rate } from 'k6/metrics';
import Client from 'https://jslib.k6.io/agento11y-evals/0.1.0/index.js';

const RUNNER = __ENV.RUNNER_URL || 'http://127.0.0.1:8098';
const PUBLISH = __ENV.EXPERIMENT_PUBLISH === 'true';
const TRIALS = Number(__ENV.EXPERIMENT_TRIALS) || 3;
const SELECTED = (__ENV.EXPERIMENT_TASKS || '').split(/[\s,]+/).filter(Boolean);
const AGENT_NAME = 'o11y-bench';

const evals = new Client({
  apiUrl: __ENV.AGENTO11Y_ENDPOINT,
  tenantId: __ENV.AGENTO11Y_AUTH_TENANT_ID,
  token: __ENV.AGENTO11Y_AUTH_TOKEN,
  grafanaUrl: __ENV.AGENTO11Y_GRAFANA_URL,
  serviceAccountToken: __ENV.AGENTO11Y_SERVICE_ACCOUNT_TOKEN,
});

const trialPass = new Rate('trial_pass');

export const options = {
  // One iteration walks every selected task and attempt, one trial at a time:
  // each trial owns a Docker stack.
  scenarios: { suite: { executor: 'shared-iterations', vus: 1, iterations: 1, maxDuration: '48h' } },
  setupTimeout: '5m',
  teardownTimeout: '5m',
};

function getJSON(path) {
  const res = http.get(RUNNER + path);
  if (res.status !== 200) throw new Error(`runner ${path} answered ${res.status}: ${res.body}`);
  return res.json();
}

// The tasks to run: every o11y-bench task, or the selected ones, in spec order.
function selectTasks() {
  const all = getJSON('/tasks');
  const unknown = SELECTED.filter((id) => !all.some((t) => t.id === id));
  if (unknown.length) throw new Error(`unknown EXPERIMENT_TASKS: ${unknown.join(', ')}`);
  return SELECTED.length ? all.filter((t) => SELECTED.includes(t.id)) : all;
}

// Pulls the published suite, narrowed to the selected tasks, and opens the experiment.
async function openExperiment(tasks) {
  const pulled = await evals.pullSuite(__ENV.AGENTO11Y_SUITE_ID, __ENV.AGENTO11Y_SUITE_VERSION);
  const ids = tasks.map((t) => t.id);
  const missing = ids.filter((id) => !pulled.cases.some((c) => c.test_case_id === id));
  if (missing.length) throw new Error(`suite ${pulled.version} lacks ${missing.join(', ')}; run make experiment-suite`);
  const suite = { ...pulled, cases: pulled.cases.filter((c) => ids.includes(c.test_case_id)) };
  const exp = await evals.createExperiment({
    id: __ENV.EXPERIMENT_ID,
    name: `${__ENV.EXPERIMENT_NAME} (k=${TRIALS})`,
    suite,
    candidate: { agent_name: AGENT_NAME, model_name: __ENV.EXPERIMENT_MODEL, git_sha: __ENV.O11Y_BENCH_SHA },
    plannedTrialCount: tasks.length * TRIALS,
  });
  return { experimentId: exp.id, suite };
}

export async function setup() {
  const tasks = selectTasks();
  console.log(`${tasks.length} task(s) x ${TRIALS} trial(s)${PUBLISH ? ', publishing to Grafana Cloud' : ', local only'}`);
  return { tasks, ...(PUBLISH ? await openExperiment(tasks) : {}) };
}

// One Harbor job: the agent solves the task and the benchmark's verifier grades it.
function runTask(taskId, attempt) {
  const res = http.post(RUNNER + '/run', JSON.stringify({ task_id: taskId, attempt }), {
    headers: { 'Content-Type': 'application/json' },
    timeout: '30m',
  });
  if (res.status !== 200) throw new Error(`runner answered ${res.status}: ${res.body}`);
  return res.json();
}

// Records the trial's conversation, usage and verdict in Agent Observability.
async function report(trial, task, graded) {
  await trial.record({ input: task.statement, output: graded.final_output, model: graded.model, agentName: AGENT_NAME });
  await trial.complete({
    cost: graded.cost === null ? undefined : graded.cost,
    inputTokens: graded.input_tokens,
    outputTokens: graded.output_tokens,
    durationMs: graded.duration_ms,
  });
  await trial.score({
    scoreKey: 'o11y_bench_reward',
    value: graded.reward,
    passed: graded.passed,
    explanation: graded.explanation || `reward ${graded.reward}`,
  });
}

async function publishedTrial(exp, suite, task, attempt) {
  const testCase = suite.cases.find((c) => c.test_case_id === task.id);
  return exp.run({ testCase, attempt }, async (trial) => {
    // A failed job throws here; run() then closes the trial as failed and the next one still runs.
    const graded = runTask(task.id, attempt);
    await report(trial, task, graded);
  });
}

function localTrial(task, attempt) {
  try {
    const graded = runTask(task.id, attempt);
    return { passed: graded.passed, explanation: `reward ${graded.reward}` };
  } catch (e) {
    return { passed: false, explanation: `error: ${e}` };
  }
}

export default async function ({ tasks, experimentId, suite }) {
  const exp = PUBLISH ? evals.experiment(experimentId, suite) : null;
  for (let attempt = 1; attempt <= TRIALS; attempt++) {
    for (const task of tasks) {
      const result = PUBLISH ? await publishedTrial(exp, suite, task, attempt) : localTrial(task, attempt);
      trialPass.add(result.passed, { task: task.id });
      console.log(`${task.id} a${attempt}: ${result.passed ? 'PASS' : 'FAIL'} · ${result.explanation}`);
    }
  }
}

// Pass@k: share of tasks with at least one passing trial. Pass^k: share with all k passing.
function passRates(history) {
  const runs = Object.values(history);
  const share = (test) => (runs.length ? runs.filter(test).length / runs.length : 0);
  return { atK: share((r) => r.some(Boolean)), powK: share((r) => r.length === TRIALS && r.every(Boolean)) };
}

export async function teardown({ experimentId }) {
  const { atK, powK } = passRates(getJSON('/summary'));
  console.log(`Pass@${TRIALS} ${(atK * 100).toFixed(1)}% · Pass^${TRIALS} ${(powK * 100).toFixed(1)}%`);
  if (!PUBLISH) return;
  const url = await evals.experiment(experimentId).finalize();
  console.log(`experiment ${experimentId}${url ? ` · ${url}` : ''}`);
}
