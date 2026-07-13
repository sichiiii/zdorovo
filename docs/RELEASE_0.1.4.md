# Zdorovo 0.1.4

This release makes automatic break selection fairer when several activity timers overlap.

Highlights:

- avoids selecting the same completed activity twice in a row when alternatives are enabled;
- waits up to ten minutes for another activity that is almost due;
- prioritises a different due activity before returning to the previous type;
- combines eye rest with a due movement or neck break where appropriate;
- persists rotation state across background-service restarts;
- keeps manual Quick start actions immediate.

Install or upgrade with:

```bash
sudo apt install ./zdorovo_0.1.4_all.deb
```
