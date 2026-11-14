---
title: "Tools Let Agents Act. Guardrails Keep Them Honest."
date: 2026-11-08
draft: false
tags: ["langchain", "langgraph", "guardrails", "tool-calling", "structured-output"]
categories: ["AI Engineering"]
---

When your agent does something, who made the call: the model or your code? It's a question I never thought to ask until I built a document assistant in LangGraph: a router, three specialist agents, four tools and a memory node. The biggest lesson wasn't about graphs at all. It was about who decides what.

## What's the Difference Between a Toolbox and a Building Inspector?

Think of tool calling as a toolbox: the model decides *which* action to take (search, read, calculate). Guardrails, on the other hand, are the building inspector: checks that validate or block what flows through the agent. LangChain implements them as middleware that can intercept execution before the agent starts, after it finishes, or around model and tool calls ([LangChain docs](https://docs.langchain.com/oss/python/langchain/guardrails)).

So how do you decide which is which? My rule of thumb:

- **Open-ended choice?** Make it a tool.
- **Non-negotiable rule?** Make it a guardrail, in code. A prompt is a request, not a rule.

My calculator tool shows both. The prompt says "use the calculator for ALL calculations" (a request). The code enforces the rule:

```python
if re.match(r"^[\d\s.+\-*/()]+$", expression):
    result = eval(expression, {"__builtins__": None})
```

Now, I'll be honest. On review, I'd tighten two things here. First, `**` still passes that allow-list, so `9**9**9` can hang the process, and `eval` stays a smell. An `ast`-based parser is safer. Second, returning `-1` on failure collides with legitimate answers, so return an explicit error instead.

Routing is a guardrail too. Anthropic describes [routing](https://www.anthropic.com/engineering/building-effective-agents) as classifying an input and sending it to a specialised follow-up task, which keeps prompts focused. Mine ends with a `case _:` fallback, so a surprise classification can't strand a request.

## Why Is a Schema Like a Customs Form?

Because goods without a completed form don't cross the border! In the same way, output without a valid schema shouldn't cross into your application:

```python
class CalculationResponse(BaseModel):
    expression: str
    result: float
    explanation: str

agent = create_agent(model=llm, tools=tools,
                     response_format=CalculationResponse)
```

With `create_agent`, LangChain captures the structured output, validates it, and returns it under `structured_response`. It uses provider-native enforcement when the model supports it and falls back to tool calling otherwise ([LangChain docs](https://docs.langchain.com/oss/python/langchain/structured-output)).

For one-shot classification, `llm.with_structured_output(UserIntent)` with a `Literal["qa", "summarization", "calculation", "unknown"]` field means the model can't invent a fifth intent. Add `Field(ge=0.0, le=1.0)` to a confidence score and out-of-range values are rejected. One schema per intent works well: answers need `sources`, summaries need `key_points`, and calculations need a numeric `result`.

## Which Downstream Habits Are Worth Keeping?

Here are a few that I'd recommend:

- **Treat tool descriptions as prompts.** Anthropic's advice is to "poka-yoke" your tools: change the arguments so mistakes are harder to make ([Anthropic](https://www.anthropic.com/engineering/building-effective-agents)).
- **Log every tool call.** Mine write JSON with inputs and outputs. When an answer looks wrong, you can trace it.
- **Allow-list what you deserialise.** My checkpointer only accepts the project's own schema classes.
- **Keep it simple.** Anthropic recommends the simplest solution that works, adding complexity only when it demonstrably helps.
- **Type your tool outputs too.** Mine return formatted strings; only the final answer is typed. That's my next refactor!

## Your Turn

What are your thoughts on this one? What belongs in a guardrail versus a prompt in your agents? I'd love to hear what's worked, what's bitten you, and what I've missed. Feel free to share your experience in the comments below!

Build well until next time.

–Josh

## References

1. LangChain, [Guardrails](https://docs.langchain.com/oss/python/langchain/guardrails)
2. LangChain, [Structured output](https://docs.langchain.com/oss/python/langchain/structured-output)
3. Anthropic, [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
