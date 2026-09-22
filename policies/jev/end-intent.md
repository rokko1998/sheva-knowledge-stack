# Jev end-intent

Decide whether the user's latest message indicates that the overall current conversation/session should now end or be postponed. Do not decide whether a subtask has finished.

## end_intent

Instructions: Is the user ending the overall current interaction?

### SESSION_END
The user clearly indicates they are finished for now, are leaving, want to stop, or intend to continue in a later session.

### CONTINUE
The user is still requesting work, giving corrections, asking a follow-up, or only marking completion of one intermediate step.

### UNCERTAIN
The message could reasonably mean either.
