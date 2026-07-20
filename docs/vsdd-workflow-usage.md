# ecc-vsdd Usage Guide

## 前提

- Claude Code 2.1.214以上
- macOSまたはLinux、Python 3.10以上（Windows nativeは未対応。WSLはLinux扱い）
- Dynamic Workflowsが有効なClaude CodeプランまたはAPI環境
- Git repository
- ECC plugin
- PRまで進める場合は`gh` CLIとpush可能なremote
- 開始元checkoutがclean

モデル、effort、Dynamic Workflowのいずれかが利用できない場合、別モデルへfallbackせず停止します。

## インストール

Claude Code内で実行します。

```text
/plugin marketplace add sc30gsw/ecc-vsdd
/plugin install ecc-vsdd@ecc-vsdd
/reload-plugins
```

plugin manifestの`dependencies: ["ecc"]`により、marketplaceの明示的なHTTPS Git sourceから`affaan-m/ECC`が自動インストール・有効化されます。projectの`.claude/settings.json`へ`enabledPlugins`を書く必要はありません。

ローカルcheckoutを直接検証する場合は次のように起動できます。

```bash
claude --plugin-dir /absolute/path/to/ecc-vsdd --agent ecc-vsdd:vsdd-orchestrator --effort high
```

インストール済みpluginでは`--plugin-dir`は不要です。

## 全自動runを開始する

Fable制御専用セッションを起動します。

```bash
claude --agent ecc-vsdd:vsdd-orchestrator --effort high
```

Claude Code内で`start`します。

```text
/ecc-vsdd:vsdd-run start mail-groups-filter https://www.notion.so/xxxx --mode auto --until pr
```

詳細な機能briefを直接渡すこともできます。

```text
/ecc-vsdd:vsdd-run start "管理者がメールグループを名前と状態で絞り込める機能。URLへ条件を保持し、API失敗時は再試行できること" --until review
```

Review完了後にPRまで延長する場合は、外部変更を改めて明示します。

```text
/ecc-vsdd:vsdd-run resume mail-groups-filter --until pr
```

briefから開始した場合、Haiku Init workerがkebab-case slugを決定します。Notion URL、既存source、または十分に詳細なbriefのいずれかが必要です。

StartのHaiku処理は2段階です。最初は明示的な`operation: bootstrap`として同梱runtimeの`bootstrap` commandだけを実行し、`vsdd/<slug>` integration worktreeと、その中の`run-state.json`だけを作って終了します。この操作はPhase 0より前なのでSteeringを要求しません。Steering完了後は別invocationの`operation: phase`としてPhase 1 Initを行い、branch/worktree identity、`bootstrap_status: READY`、Init pending、追加artifactなしを機械検証してからskeletonを作ります。この正確なbootstrapは既存spec衝突として扱いません。

### start options

| Option | Default | 意味 |
| --- | --- | --- |
| `--mode auto\|standard` | `auto` | 表示・対話スタイル。モデルとgateは変わらない |
| `--base <ref>` | detected repository default | `origin/HEAD`等から検出するintegration branchのcleanな起点。曖昧なら明示が必要 |
| `--until review\|pr` | `review` | 独立reviewまで、またはpush/PR作成まで |

`--until pr`は外部変更の明示的な許可です。許可されるのは、現在の1行の`start|resume ... --until pr`プロンプトだけです。session ID・canonical cwd・prompt IDへ結び付けられ、別のユーザープロンプトが送られると消去されます。失敗したgateを無視する許可ではありません。PR worker起動時に一度だけ消費され、実際のagent IDへランダムcapabilityを結び付けます。この許可と現行review証跡がなければpush/PR操作を開始できません。

要求したReviewまたはPR境界では、成果物snapshotに加えてruntime terminal gateが`status: COMPLETE`と`reached`を保存します。ReviewからPRへ延長するときだけ、明示`--until pr`を`extend` gateが記録し、runをPhase 9へ再オープンします。

## 実行中の流れ

```text
Steering(Opus xhigh, stale時のみ)
  → Init(Haiku low)
  → Requirements(Opus xhigh)
  → Requirements Review(新規Opus xhigh)
  → Design(Opus xhigh)
  → Tasks(Sonnet high)
  → Plan Review(新規Opus xhigh)
  → Implementation Plan(Sonnet ultracode)
  → Workflow Review(新規Opus xhigh)
  → Implementation(同じSonnet ultracode session)
  → Code Review + Security Review(別々の新規Opus xhigh)
  → 必要ならRemediation(Sonnet high / ultracode)
  → PR(Sonnet medium)
```

Fableは次phaseを選び、workerを起動し、固定`verdict`を確認するだけです。Skill hookがFableのWrite/Edit、任意Bash、未固定agent起動、per-invocation model overrideを拒否します。Claude Codeはplugin subagentのhookを無視するため、`UserPromptSubmit` hookがplugin同梱定義から13個のproject-local protected workerを`.claude/agents/`へ一時生成し、実install先のPreToolUse guardを埋め込みます。agent registryはprompt受付前に固定されるため、初回の親Fableはprompt-bound relayで同じコマンドをdetached child Fable sessionへ1回だけ引き継ぎ、45秒単位でterminalまでpollします。childはstartup時から登録済みのunscoped worker名だけを起動でき、生成物hashとsession/cwd/prompt identityを通過したworkerだけが自動許可されます。`SubagentStart`は実インストール先のruntime/launcher/brokerのliteral pathも注入するため、workerのBash環境変数やfilesystem探索には依存しません。生成物は`SessionEnd`で削除され、混在モデルのorchestrator sessionではglobal `CLAUDE_CODE_SUBAGENT_MODEL`も固定値にできません。

全workerは無人実行contextを受け取るため、Requirementsの7項目を含むphase内質問や`CONFIRM`で停止しません。保存済みソースから安全に決められない製品・データ損失・security・compatibility・破壊的操作・外部権限の判断だけが`BLOCKED`になります。

## 状態を確認する

```text
/ecc-vsdd:vsdd-run status mail-groups-filter
```

次を表示します。

- 現在phaseとattempt
- 各phaseのmodel / effort
- artifact hashとtarget commit
- review verdict
- blocker evidence
- integration/TASK worktree
- implementation session ID
- resume command

## 中断から再開する

```text
/ecc-vsdd:vsdd-run resume mail-groups-filter
```

`resume`はartifact hashとcommitを再検証します。入力が変わっていれば、その影響を受けるphase以降を自動無効化し、stale hashを取り除いて再実行します。workerが上流成果物を正規に再生成してsnapshotした場合も同じ依存無効化が走ります。古いcommitに対するreviewは再利用しません。PR前には全必須reviewのOpus/xhigh snapshotと`target_commit == HEAD`を再検証します。

再開時に新しいsourceを追加・差し替える場合は第3引数に渡します。

```text
/ecc-vsdd:vsdd-run resume mail-groups-filter https://www.notion.so/yyyy
```

既存skeletonは維持し、取得成功後にRequirements以降を無効化します。指定URLを取得できなければ停止し、以前のsourceへ黙ってfallbackしません。

Dynamic Workflowのsession IDはlauncherが`run-state.json`へ保存します。起動後はlauncher-owned detached supervisorの証跡pathを45秒単位のforeground `wait`で繰り返し監視します。同じstageの生存中supervisorは自動再利用されるため、Fableのcompactionやsession再開後も二重起動しません。Implementation PlanがOpus PASSした後は、launcher自身がcurrent snapshotとsession IDを検証してから同じSonnet ultracode sessionを再開します。review roundとTASK attemptは永続counterで数え、3回目のREVISE/FAILで自動的にBLOCKEDになります。

## 停止とcleanup

```text
/ecc-vsdd:vsdd-run cancel mail-groups-filter
/ecc-vsdd:vsdd-run cleanup mail-groups-filter
```

`cancel`は新しい処理を止めるだけで、変更やworktreeを削除しません。`cleanup`は統合済みTASK worktreeだけを安全確認後に削除します。PR作成後もintegration worktreeは確認用に保持します。

## BLOCKEDになった場合

```text
VSDD RUN BLOCKED: mail-groups-filter
Phase: implementation-plan-review
Attempt: 3/3
Evidence: .claude/specs/mail-groups-filter/review-results/implementation-workflow-review.md
Preserved state: .../run-state.json
Resume: /ecc-vsdd:vsdd-run resume mail-groups-filter
```

主なblock条件:

| 条件 | 対応 |
| --- | --- |
| required model / effort unavailable | 利用可能なplan・管理設定を確認。fallbackはしない |
| Dynamic Workflows disabled | `/config`または`disableWorkflows`管理設定を確認 |
| dirty source checkout | 変更をcommit/stashし、cleanな`--base`から再開 |
| repository defaultが曖昧 | `--base origin/develop`のように明示してstart |
| Steering Open/DRAFT/Glossary pending | sourceまたはSteeringを確定してresume |
| TASK set mismatch | `tasks.md`と`progress.md`のTASK行を完全一致させてresume |
| product/security/compatibility decision missing | ユーザーが仕様を決定してsourceを更新 |
| Requirements / Plan / Workflow review 3回失敗 | artifactを手動確認し、上流入力を修正してresume |
| TASK 3attempt失敗 | failure evidenceと依存TASKを確認し、仕様または実装条件を修正 |
| Code/Security review修正上限 | CRITICAL/HIGHを確認し、上流spec変更として再実行 |
| PR broker / push / `gh` failure | auth、remote、権限を修正し、新しいexact `resume ... --until pr`で再開 |

## review修正の自動切替

通常のCRITICAL/HIGH修正は新規Sonnet `high`で行います。次のどちらかならSonnet `ultracode`へ切り替えます。

- Opus reportが`remediation_mode: workflow`
- 通常修正後の再reviewでもCRITICAL/HIGHが残る

修正後は毎回、新しいCode OpusとSecurity Opusが同じ新commitをreviewします。

## PRの状態

- CRITICAL/HIGHあり: PRを作成しない
- blocking findingなし、MEDIUM/manual follow-upあり: Draft PR
- blocking findingなし、MEDIUM/manual follow-upなし: Ready PR

どちらのPR状態でも、guardが観測できる直接commandと一般的なshell/interpreter wrapperでは、全workerの`git push`、`git send-pack`、`gh pr`/`gh api`変更操作を拒否します。PR workerは`pr-body.md`だけを作り、`SubagentStart`で注入されたcapability/session/agent IDを専用brokerへ渡します。brokerだけがpreflightをpush前とPR作成前に再実行し、remote base、pushed head、GitHub base/head/draft identityを検証して`pr-result.json`を原子的に保存します。current integration `HEAD`に対するruntime snapshotが成功しなければPhase 9は未完了です。

hookはClaude Codeが観測する通常のtool commandを防御しますが、任意バイナリや難読化されたスクリプトの内部通信までOSレベルで遮断するsandboxではありません。信頼できないworker/toolにはGitHub資格情報を渡さず、送信network policy、protected branch/ruleset、最小権限tokenを併用してください。

## Phaseを個別実行する

各Skillを直接呼んでも、成果物作成は指定workerへ委譲されます。

```text
/ecc-vsdd:vsdd-steering
/ecc-vsdd:vsdd-init mail-groups-filter --mode auto
/ecc-vsdd:vsdd-requirements mail-groups-filter
/ecc-vsdd:vsdd-review-requirements mail-groups-filter
/ecc-vsdd:vsdd-design mail-groups-filter
/ecc-vsdd:vsdd-tasks mail-groups-filter
/ecc-vsdd:vsdd-review-plan mail-groups-filter
/ecc-vsdd:vsdd-impl mail-groups-filter
/ecc-vsdd:vsdd-review mail-groups-filter
# Phase 9の外部publicationはmanaged runのexact promptだけで許可
/ecc-vsdd:vsdd-run resume mail-groups-filter --until pr
```

`/vsdd-impl <slug> TASK-001`のようなTASK単位実行は自動workflowでは使用しません。`tasks.md`全体をSonnet Dynamic Workflowが読み、実行方法を決定します。

## Artifact layout

```text
.claude/specs/
├── _steering/
│   ├── tech.md
│   ├── structure.md
│   ├── context.md
│   └── open-questions.md
└── <slug>/
    ├── source-notion.md
    ├── source-request.md
    ├── requirements.md
    ├── design.md
    ├── tasks.md
    ├── implementation-workflow.md
    ├── implementation-ledger.md
    ├── progress.md
    ├── change-log.md
    ├── run-state.json
    ├── worker-sessions/
    └── review-results/
        ├── requirement-review.md
        ├── plan-review.md
        ├── implementation-workflow-review.md
        ├── code-review.md
        └── security-review.md
```
