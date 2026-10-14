# The terminal half of docs/img/walkthrough.gif. Run from docs/img/src: `vhs walkthrough.tape`
# Needs: vhs, evalstone on PATH (pip install evalstone). Writes walkthrough-terminal.mp4.
Output walkthrough-terminal.mp4
Set Shell "bash"
Set FontSize 20
Set Width 1280
Set Height 720
Set Padding 28
Set TypingSpeed 45ms
Set Theme "Catppuccin Latte"

Hide
Type "SRC=$PWD; DEMO_DIR=${DEMO_DIR:-/Users/Shared/my-bot}; rm -rf $DEMO_DIR && mkdir -p $DEMO_DIR/prompts && cp $SRC/new-prompt.jsonl $DEMO_DIR/prompts/new.jsonl && cp $SRC/fixed-prompt.jsonl $DEMO_DIR/prompts/fixed.jsonl && cd $DEMO_DIR && export PS1='$ ' COLUMNS=90 && clear"
Enter
Sleep 500ms
Show

Type "evalstone --version"
Enter
Sleep 1500ms
Type "evalstone init"
Enter
Sleep 2500ms
Type "evalstone gate nightly -r report.json"
Enter
Sleep 4s
Type "clear"
Enter
Type "# a new prompt ships, and one answer regresses"
Enter
Type "cp prompts/new.jsonl evals/outputs.jsonl"
Enter
Sleep 300ms
Type "evalstone gate nightly -r report.json; echo exit=$?"
Enter
Sleep 8s
Type "clear"
Enter
Type "# fix the prompt, gate again"
Enter
Type "cp prompts/fixed.jsonl evals/outputs.jsonl"
Enter
Sleep 300ms
Type "evalstone gate nightly -r report.json; echo exit=$?"
Enter
Sleep 5s
