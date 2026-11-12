---
name: routing
description: Show or control the model-routing system (status, on, off, fable on/off, log).
argument-hint: "[status|on|off|fable on|fable off|log]"
disable-model-invocation: true
allowed-tools: Bash(node:*)
---

Output of the routing control command:

!`node "${CLAUDE_SKILL_DIR}/../../hooks/router.mjs" $ARGUMENTS`

Show the output above to the user as-is, in Arabic, in a short code block. Do not run any other command and do not analyse further unless asked. If the user turned routing on or off, remind them it applies to new sessions.
