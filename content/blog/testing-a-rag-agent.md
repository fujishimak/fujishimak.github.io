---
title: "Testing a RAG Agent: Grade the Librarian and the Student Separately"
date: 2026-11-08
draft: false
tags: ["langchain", "rag", "deepeval", "evaluation", "testing"]
categories: ["AI Engineering"]
---

Have you ever gotten a wrong answer out of a RAG system and had no idea whose fault it was? Here's the thing: RAG is an open-book exam. The retriever is the librarian who fetches the books; the LLM is the student who writes the answer. A wrong answer could mean the wrong books or bad reading. And if you only grade the essay, you can't tell which!

To see this in action, I built an energy-advisor agent with seven tools, one of them a RAG search over a Chroma store, and evaluated it with DeepEval on ten test cases. Let's walk through what I found.

## How Should You Write Your Test Cases?

Like a rubric, not an answer key. LLM output varies from run to run, so don't assert exact strings. Instead, pair each question with the tools you expect and a description of a good answer:

```python
{"id": "appliance_1",
 "question": "How much can I save running my dishwasher off-peak?",
 "expected_tools": ["get_electricity_prices", "calculate_energy_savings"],
 "expected_response": "Compare peak and off-peak rates, recommend a start "
                      "time, and quantify savings with the basis stated"}
```

You may be wondering where to even begin with evals. Hamel Husain frames them in levels, starting with fast, scoped unit tests before human review and A/B testing ([Husain](https://hamel.dev/blog/posts/evals/)).

## The Essay Reads Well. The Trajectory Doesn't.

Now this is where it gets interesting. One run, ten cases, mean scores:

| Metric | Mean |
|---|---|
| Answer relevancy | 0.92 |
| Tool correctness | 0.53 |
| Accuracy (G-Eval) | 0.57 |
| Completeness (G-Eval) | 0.63 |

Looks great at first glance, right? That 0.92 is hiding something. Relevancy asks "is this on topic?", not "did the agent do the work?". For "How much would I save cutting HVAC usage by 20%?", the agent replied by asking me for my usage figures instead of calling the usage tool. Relevancy: 1.0. Tool correctness: 0.0. DeepEval's [tool correctness](https://deepeval.com/docs/metrics-tool-correctness) compares the tools called with those expected, and its core score needs no judge model.

Here's another one. An answer confidently recommended charging "tomorrow (October 7, 2023)". And guess what? I never told the agent today's date, so it made one up! Relevancy couldn't see that. The fix is simple: pass the current date in context.

## Does Your Judge Have the Right Rubric?

[G-Eval](https://deepeval.com/blog/top-5-geval-use-cases) scores against custom criteria that you write yourself. The paper reports a 0.514 Spearman correlation with humans on summarization ([Liu et al.](https://arxiv.org/abs/2303.16634)). That's better than earlier methods, but it's not perfect, so do spot-check your judge.

```python
class CompletenessMetric(GEval):
    def __init__(self, model=None, threshold=0.5):
        super().__init__(
            name="Completeness",
            criteria="Does the answer give a specific time, a cost "
                     "estimate, and a rationale?",
            evaluation_params=[LLMTestCaseParams.INPUT,
                               LLMTestCaseParams.ACTUAL_OUTPUT,
                               LLMTestCaseParams.EXPECTED_OUTPUT],
            model=model, threshold=threshold)
```

You see, my one shared rubric demands a time and a cost, so my out-of-scope case scored 0.15. The rubric was wrong, not the agent! Write rubrics per question type, and keep your expectations consistent. I'll admit I slipped here: I expected a polite decline yet also expected a search call. Pick one!

## What About the Librarian's Report Card?

It's still blank. DeepEval's RAG triad is answer relevancy, faithfulness and contextual relevancy, each pointing at a different knob: prompt template, LLM choice, and chunk size, top-K or embedding model ([DeepEval](https://deepeval.com/guides/guides-rag-triad)). I measured only the first.

Interestingly enough, my setup was hiding the librarian's mistakes. My corpus is four chunks, so a top-3 search returns most of it. "Pool pump scheduling" returned a dishwasher tip, and the tool labels top-ranked results "high" by position alone. Retrieval couldn't visibly fail. The way out is to pass retrieved chunks as `retrieval_context` and let the contextual metrics tell you the truth.

## Which Habits Paid Off?

- **Seed your mocks.** My price tool seeds its generator with the date, so reruns are comparable.
- **Pin the judge.** Temperature 0, same model every run.
- **Test the test harness.** My first tool-extraction helper was wrong, and bad instrumentation gives you confident, wrong scores. Naturally, that's the worst kind.
- **Cover the edges.** Out-of-scope and missing-data questions expose what happy paths hide.

## Your Turn

What are your thoughts on this one? How do you test your agents and RAG pipelines? Which metrics have earned your trust, and which ones misled you? It would be great to share your experience or feedback in the comments below!

Test well until next time.

–Josh

## References

1. DeepEval, [RAG triad](https://deepeval.com/guides/guides-rag-triad)
2. DeepEval, [Tool correctness](https://deepeval.com/docs/metrics-tool-correctness)
3. DeepEval, [Top 5 G-Eval use cases](https://deepeval.com/blog/top-5-geval-use-cases)
4. Liu et al., [G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment](https://arxiv.org/abs/2303.16634)
5. Hamel Husain, [Your AI Product Needs Evals](https://hamel.dev/blog/posts/evals/)
