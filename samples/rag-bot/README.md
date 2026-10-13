# rag-bot sample

A tiny retrieval-augmented support bot (keyword retrieval over `docs/policy.md`,
no LLM, so it runs anywhere) and the eval suite that catches its mistakes.

```bash
cd samples/rag-bot
pip install evalstone            # or: pip install -e ../../python/evalstone
evalstone list
evalstone run nightly            # table + evalstone-report.json
evalstone gate nightly           # exit 1 when the gate fails
```

What you will see: the bot answers most questions from the right paragraph and
some from the wrong one. The `must_include` check catches those, the gate
(`min_pass_rate: 0.9`) fails, and the report lists the failing samples with the
reason. Fix the retriever (or the docs) and run again.

`evals/checks.py` shows project-specific checks registered with `@check`;
`evalstone.yaml` shows keyed built-in checks (`contains`, `length`).
