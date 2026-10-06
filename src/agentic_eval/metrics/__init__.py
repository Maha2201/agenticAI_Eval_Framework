"""Built-in metrics, grouped by what they evaluate.

trajectory   agent_path
tools        tool_selection, tool_arguments, forbidden_tools, tool_scope
state        final_state, final_response
safety       guardrails, rejected_handoffs, approval_before_write
operational  latency
deepeval     deepeval_tool_correctness   (needs the 'deepeval' extra)
rubric       llm_rubric                  (needs a judge)
"""
