# Handlers package — one module per autonomous agent.
#
# Module names use underscores; agent names use hyphens. The
# dispatcher in agent_runner.py translates `aws-cost-sentinel` ->
# `aws_cost_sentinel`. Each module must expose
# `handle(event, context) -> dict`.
