---
title: "The Supervisor Should Be Code. The Knowledge Base Can Be SQLite."
date: 2026-11-23
draft: false
tags: ["langgraph", "multi-agent", "rag", "sqlite-vec", "architecture"]
categories: ["AI Engineering"]
---

What happens when five agents share one customer ticket? I built a support desk in LangGraph to find out: a classifier, an account clerk, a service desk, a resolver and an escalation agent, plus an orchestrator that decides who works next. The surprise wasn't the agents. It was how much better the system got once I stopped letting a model run the meeting.

## Why Is the Supervisor Code?

I tried `langgraph-supervisor` first. The order of steps came out right, but the bookkeeping fell apart. The service desk agent reported creating a ticket that was never created. Hand-offs carried no task, so the next agent guessed. Tool results were hidden from the supervisor, so the ticket id vanished between steps. That's three failures behind one confident reply!

So the hub became a router written in code. It reads the saved state and picks the next node: classify, look up the account, create the ticket, recall memory, resolve, escalate, respond. Every spoke returns to the hub, and a `phase` field carries the conversation across turns (`intake`, `processing`, `awaiting_confirmation`, `escalated`, `closed`). The model still does what needs judgement: labelling the issue, searching, writing the reply. The order of side effects belongs to code.

Ids come from tool results, never from prose. If `create_ticket` did not return `ok: true`, no ticket exists, no matter what the model says. That one rule removed a whole class of lies.

## Why Keep Vectors in SQLite?

Because a support desk already owns a database, and a second one is a second thing to back up, secure and explain. The `knowledge` table stays the source of truth. Beside it, `sqlite-vec` adds a virtual table with one 1536-dimension vector per article, cosine distance, rebuilt in a single transaction:

```sql
CREATE VIRTUAL TABLE vec_knowledge USING vec0(
  article_id text primary key,
  account_id text,
  embedding float[1536] distance_metric=cosine);
```

`sqlite_vec.load()` runs on every SQLAlchemy connection, and articles, tickets and customer memory all live in `udahub.db`. Search returns `score = 1 - distance`, clamped to 0..1, and the resolver may only answer from articles above 0.32. I calibrated that on fifteen articles: real questions scored 0.34 to 0.55, an off-topic one scored 0.10. In my last run the confident searches landed at 0.35, 0.42, 0.43, 0.50, 0.56 and 0.60; the miss scored 0.16 and escalated. Small sample, honest caveat.

The grounding check is code too. A Pydantic validator on `Resolution` empties any answer that cites no article, so ungrounded text cannot reach the customer.

## Does the Architecture Hold Up?

Across nine scripted tickets: three resolved, five escalated, each escalation with its own reason code (`urgent_complex`, `low_confidence`, `account_blocked`, `fix_failed`, `repeat_issue`). That spread matters more than a resolution rate. Every hand-off has a named cause I can read in the log, and the log holds no customer names or emails.

Memory earns its place by changing decisions, not decoration. A `customer_memory` table keeps resolved issues and stated preferences. Recall reads it before the search, so replies follow a customer's language preference, and a customer whose problem in the same category was fixed twice before is escalated without another search. The standard fix evidently does not last; repeating it a third time is not service.

The cost is latency: a full turn takes 20 to 30 seconds because several model calls sit between the customer and the reply.

Now, before those numbers impress anyone: this is a capstone, not a production service. CultPass is fictional, `escalate_to_human` reports "Human notified" and reaches no one, and every component runs in one process on one machine. Here is what would have to change before a real customer touched it.

## What Would Break in Production?

### The Database Becomes a Service

`sqlite-vec` brute-forces the search: every query compares against every vector. At fifteen articles that is free; at fifty thousand it is a scan per question. SQLite also gives you one writer, and a support queue is many writers. I would move tickets, memory and vectors to Postgres with `pgvector` or a managed vector store, keep the same `1 - distance` contract, and add an approximate index. Conversation checkpoints already live in their own file; in production they need retention limits and the same privacy treatment as tickets.

### The Tool Layer Needs Adult Supervision

The MCP servers are in-process, unauthenticated and never retry. Tools that return errors instead of raising is a good start, but my `create_ticket` is a side effect: a timeout after the insert can become a duplicate on retry. Production needs idempotency keys on writes, timeouts with bounded retries, and an outbox or queue behind escalation instead of a print statement. Add per-tenant authentication and least privilege on both servers, and assume a tool will eventually answer twice.

### Routing Needs Evidence, Not Fifteen Articles

This concerns my choice of thresholding for the project. Production would calibrate them per tenant against real resolved tickets, watch for drift as the knowledge base changes, and keep last month's transcripts as a regression set. Latency needs streaming, a cheap model for classification, and a degraded path when the provider is down. Then add rate limits, cost budgets and a circuit breaker. Code-owned routing is easy to test, but every new exception becomes a code change, so the graph itself needs versioning and replayable state.

## What Should You Take Away?

- Put the order of side effects in code and the judgement in prompts.
- Take ids from tool results, not model prose.
- Keep vectors beside your rows until scale says otherwise.
- Calibrate the confidence threshold, then re-calibrate on real traffic.
- Treat a working demo as a hypothesis, not a deployment.

## Your Turn

What are your thoughts on this one? Do you let a model supervise your agents, or does your code hold the gavel? If you have run multi-agent systems in production, I would love to hear where the hand-offs broke first. Feel free to share your experience in the comments below!


–Josh

## References

1. LangGraph, [Multi-agent systems](https://langchain-ai.github.io/langgraph/concepts/multi_agent/)
2. sqlite-vec, [Vector search in SQLite](https://github.com/asg017/sqlite-vec)
3. Anthropic, [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
