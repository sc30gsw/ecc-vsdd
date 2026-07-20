# Changelog

このプロジェクトの主な変更を記録します。バージョンは[Semantic Versioning](https://semver.org/)に従います。

## [1.0.0-rc.3] - 2026-07-17

### Added

- Fable `high`を制御面に限定し、成果物作成を固定model/effortの15 agentへ委譲する10フェーズのVSDD orchestrator。
- Requirements、Plan、Implementation Workflow、Code、Securityの独立Opus `xhigh` reviewと永続attempt ledger。
- Sonnet `ultracode` Dynamic Workflowによる`tasks.md`全体の計画、TDD実装、worktree統合、TASK-to-SHA証跡。
- artifact hash、上流変更時の依存無効化、Open/DRAFT再検査、TASK集合一致、base branch検出、resume/source-updateを扱う決定的runtime state machine。
- prompt/session/cwd/agentへ束縛したPR同意と、remote/GitHub identityを検証するcapability-gated PR action broker。
- Linux/macOS、Python 3.10/3.13のtest・subprocess coverageとClaude Code strict plugin validationを行うCI。
- MIT Licenseとplugin manifestのSPDX license metadata。

### Changed

- `--until review`を安全な既定境界とし、PR publicationは現在のexact `start|resume ... --until pr`プロンプトだけで許可。
- Review修正は通常Sonnet `high`、cross-cuttingまたは再失敗時だけSonnet `ultracode`へ昇格。
- plugin依存をmanifestの`dependencies`で解決し、project `.claude/settings.json`の`enabledPlugins`を不要化。

### Fixed

- 無人runがphase内質問やconfirmationで停止する問題。
- Requirements以降で増えたOpen Questionを下流phaseが見逃す問題。
- `main`固定により実際のdefault branchへ直接commitし得る問題。
- 上流artifact変更後に古いreview/design/tasksを再利用する問題。
- resume時に追加したNotion sourceを無視する問題。
- `tasks.md`と`progress.md`のTASK欠落を完了扱いする問題。
- stale review attempt、別commitのreview、未統合TASK commit、偽のPR完了メッセージを受理する問題。
- top-level Fable sessionがCLI既定の`medium` effortで起動し、control-plane preflightで停止する問題。起動例と契約で`--effort high`を必須化。
- plugin-level hookがsubagent内部のtool callには継承されず、`dontAsk`無人実行でworkerのWrite/Bashが拒否される問題。全worker agent frontmatterへ同じPreToolUse guardを同梱。
- subagentのBash環境に`CLAUDE_PLUGIN_ROOT`が継承されず、workerがplugin install先を探索する問題。`SubagentStart`でruntime/launcher/brokerのliteral pathを注入。

### Security

- worker agent frontmatterのPreToolUse guardが、観測できる直接commandと一般的なshell/interpreter wrapperで全workerの`git push`、`git send-pack`、GitHub mutation commandを拒否し、PR brokerを唯一の対応経路に変更。
- private runtime recordをowner/mode/regular-file/link-countで検証し、symlink・hard link・FIFO・unsafe modeをfail-closedで拒否。
- record作成を`O_EXCL`/`O_NOFOLLOW`、期限切れ状態をSessionStart sweep、PR同意をone-shot消費に変更。

## 0.3.x - 2026-07

- `review|pr` terminal gate、明示的なPR延長、PR evidence snapshot、session-bound PR preflightを段階的に導入。
- launcher-owned supervisor、workflow run ID、task gate、review attempt整合性を追加。

## 0.2.x - 2026-07

- unattended phase contract、mixed-model routing、implementation workflow review、runtime state検証を追加。

## 0.1.x - 2026-07

- 初期のVSDD Skill群、Steering、EARS requirements、design/tasks、TDD、review、PR traceabilityを公開。
