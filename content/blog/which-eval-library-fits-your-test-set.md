---
title: "Which Eval Library Fits Your Test Set?"
date: 2026-11-13
draft: false
tags: ["evaluation", "deepeval", "ragas", "mlflow", "langgraph"]
categories: ["AI Engineering"]
---

Do you remember the last time you picked a tool because it was the popular one, and then spent the week bending your data to fit it? I sure do! On my latest project I did exactly that, and guess what I ended up building before I had measured a single thing? Adapters.

Here's the short version. An eval library is a ruler. If it measures in units you don't have, you spend your time converting instead of measuring. I was evaluating an energy-advisor agent (seven tools, one of them a Chroma RAG search, and ten test cases). I started with RAGAS and finished with DeepEval. You'll see why as you read on, and what the final report looks like. I covered the RAG triad in [Testing a RAG Agent: Grade the Librarian and the Student Separately](/blog/testing-a-rag-agent/); this post is about the harness.

## So What Got in the Way With RAGAS?

RAGAS is a capable library, and version 0.3.5 is in my lockfile. The friction was a mismatch with my data. You see, each metric declares the fields it needs, and three of them didn't fit:

- **Reference answers.** `FactualCorrectness` needs a `response` and a `reference`. My test cases hold a rubric ("recommend a start time, quantify savings"), because prices and weather change by day, so there is no gold answer to write.
- **Tool calls.** `ToolCallAccuracy` is a multi-turn metric that needs `reference_tool_calls`, which means names and arguments, in [RAGAS's own sample types](https://docs.ragas.io/en/stable/concepts/components/eval_sample/). My expectations were tool names, and my traces were LangChain messages.
- **Wiring.** Every judge-based metric needs an LLM wrapper pointed at my proxy endpoint, and the relevancy metrics need embeddings too.

None of it was impossible. But I was building adapters before I had measured anything, and that's when I knew it was time to step back.

## Fine, But Why Did DeepEval Fit?

Because it asked for the data I already had! DeepEval's `LLMTestCase` takes `input`, `actual_output`, `expected_output`, `tools_called` and `expected_tools`. The rubric goes straight into `expected_output`, and one judge object serves every metric:

```python
llm_judge = GPTModel(model="gpt-4o-mini", temperature=0.0,
                     base_url=os.environ["OPENAI_BASE_URL"],
                     api_key=os.environ["VOCAREUM_API_KEY"])
```

## Stock for the Universal, Custom for the Domain

Think of the stock metrics as the everyday tools in the drawer. I used the stock `AnswerRelevancyMetric` for "is this on topic?". For qualities specific to my agent, I subclassed `GEval` so the criteria are fixed and callers only pass the judge:

```python
class UsefulnessMetric(GEval):
    def __init__(self, model=None, threshold=0.5, **kwargs):
        super().__init__(
            name="Usefulness",
            criteria="Does the answer include concrete, actionable steps, "
                     "specific times or settings, and clear next steps?",
            evaluation_params=[LLMTestCaseParams.INPUT,
                               LLMTestCaseParams.ACTUAL_OUTPUT,
                               LLMTestCaseParams.EXPECTED_OUTPUT],
            model=model, threshold=threshold, **kwargs)
```

Accuracy and Completeness follow the same pattern. Completeness compares against `expected_output`, so one metric works across EV, thermostat, appliance and solar questions.

## What About Tool Correctness?

I began with the stock `ToolCorrectnessMetric`. It scores tool selection only when you pass `available_tools`, and it returns one combined number. I wanted completeness, appropriateness, and a list of what was missed or unnecessary. Set arithmetic does all of that with no judge call at all:

```python
called = {c.name for c in extract_tools_called(messages)}
expected = set(expected_tools)
correct, missing, unnecessary = called & expected, expected - called, called - expected
return {"completeness_score": len(correct) / len(expected) if expected else 0,
        "appropriateness_score": len(correct) / len(called) if called else 0,
        "correct_tools": sorted(correct), "missing_tools": sorted(missing),
        "unnecessary_tools": sorted(unnecessary)}
```

My rule of thumb? Use an LLM judge for taste, and plain code for facts.

## Does One Aggregated Report Tell You Enough?

`generate_evaluation_report` collects the per-test scores, then hands them to `calculate_statistics`, which returns overall means, strengths, weaknesses and recommendations. A separate `display_evaluation_report` prints it. My latest run:

| Metric | Mean |
|---|---|
| Relevance | 0.89 |
| Completeness | 0.74 |
| Accuracy | 0.72 |
| Usefulness | 0.80 |
| Tool completeness | 0.77 |
| Tool appropriateness | 0.92 |

Looks pretty good, right? Not so fast! The averages were kind. The weaknesses section read "(none)" while one out-of-scope case scored 0.0 and `search_energy_tips` was skipped in three tests. Means hide individual failures, so report pass rates and list the failing cases too.

## Can You Track This in MLflow?

You can, and it's easier than you might think. The report is plain numbers plus a nested dict, so it maps onto MLflow's tracking APIs. This is a sketch; I haven't run it:

```python
with mlflow.start_run(run_name="energy-advisor-eval"):
    mlflow.log_metrics(report["overall"])
    mlflow.log_dict(report["per_test"], "per_test.json")
```

Log the prompt version as a parameter, and you can compare runs side by side as the prompt changes.

## What Should You Take Away From This?

- Choose the library whose required inputs match the data you actually have.
- Mix stock metrics, custom judges and deterministic code.
- Pin the judge model and temperature.
- Report aggregates and failures together.

## Your Turn

What are your thoughts on this one? Which eval library has fit your data best, and where did the adapter work cost you? If you've got an opinion, please feel free to share it in the comments. I'd love to hear more from you!

Eval well until next time.

–Josh

## References

1. RAGAS, [Evaluation sample](https://docs.ragas.io/en/stable/concepts/components/eval_sample/)
2. RAGAS, [Agentic or tool use metrics](https://docs.ragas.io/en/v0.3.3/concepts/metrics/available_metrics/agents/)
3. DeepEval, [Tool correctness](https://deepeval.com/docs/metrics-tool-correctness)
4. DeepEval, [Top 5 G-Eval use cases](https://deepeval.com/blog/top-5-geval-use-cases)
5. MLflow, [Tracking APIs](https://www.mlflow.org/docs/3.6.0/ml/tracking/tracking-api/)
