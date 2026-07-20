# Changelog

このプロジェクトの主な変更を記録します。バージョンは[Semantic Versioning](https://semver.org/)に従います。

## [1.0.0-rc.11] - 2026-07-21

### Fixed

- Claude Codeがproject agent registryを`UserPromptSubmit`より前に固定するため、初回の同一sessionでは一時生成workerが見つからない問題。親Fableをprompt-bound relayで1回だけchild sessionへ引き継ぎ、生成済みworkerをstartup時から登録した状態で同じVSDDコマンドを無人続行。childはdetachし、親は45秒単位でpollするため長時間runを単一Bash呼出しへ束縛しない。
- project agent frontmatter hookを公式schemaどおり単一の`command`文字列として生成し、`dontAsk`でも検証済みのWrite/Edit/Bashを明示許可できるよう修正。
- bootstrapのclean checkout判定も同じ単一`command`形式を認識するよう同期し、生成proxyだけを安全に除外。
- relay childへClaude Code公式の`--add-dir`でprivateなmanaged worktree rootを付与し、隔離worktreeを明示的なファイルアクセス境界として登録。
- relay childを`acceptEdits`で起動し、Fableのglobal guardを維持しつつ、subagentが追加済みmanaged worktree内の編集と一般的なファイル操作を無人実行できるよう修正。
- integration worktreeを`/tmp/vsdd-worktrees/<slug>`へ固定し、Fableが`--add-dir`の外にsibling worktreeを選ぶ経路を除去。

## [1.0.0-rc.5] - 2026-07-17

### Fixed

- Claude Codeがplugin subagentの`hooks`を無視するため初回無人runのWrite/Bashが拒否される問題。VSDD開始時に13個の保護済みproject agentを一時生成し、実install先のguard pathと生成物hashを検証して、`SessionEnd`で削除する方式へ変更。異常終了後はprivate recordとhashが一致するproxyを次sessionが安全に引き継ぎ、期限切れ時に回収。

### Security

- Fableからplugin-scoped workerを起動する経路を拒否し、session/cwd/promptへ束縛されたunscoped project workerだけを許可。bootstrapのclean判定は正確なmarkerを持つ生成proxyだけを除外。

## [1.0.0-rc.4] - 2026-07-17

### Changed

- worker frontmatter hookと`CLAUDE_PLUGIN_ROOT`の実機検証に合わせ、最低Claude Code versionを2.1.214へ更新。

### Security

- `PreToolUse`拒否を終了コード依存から明示的な`permissionDecision: deny`へ変更し、subagent内でも安全にfail-closedするよう修正。

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
