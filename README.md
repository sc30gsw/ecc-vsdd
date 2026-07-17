# ecc-vsdd — VSDD 思想に基づく仕様駆動開発ワークフロー

**仕様（spec）を唯一の真実の源**として、Steering → 要件定義 → 設計 → タスク分解 → TDD 実装 → 検証 → PR を **10フェーズ + 厳格な検証ゲート**で機械的に強制する Claude Code プラグインです。`/vsdd-run`を使えば、モデルとeffortを固定した全フェーズを1コマンドで再開可能に連鎖実行できます。

VSDD（Verified Spec-Driven Development）の思想を、ECC プラグインのスキル・エージェント群の上に実装しています。

## 名前の由来

**ecc-vsdd** = **ecc**（everything-claude-code）+ **VSDD**（Verified Spec-Driven Development）

| 要素 | 由来 |
| --- | --- |
| **ecc** | [everything-claude-code](https://github.com/affaan-m/ECC)（現 ECC）。本ワークフローは ECC プラグインのスキル・エージェント（`ecc:plan` / `ecc:tdd-workflow` / `ecc:code-review` 等）を実行基盤として利用している |
| **VSDD** | SDD・TDD・VDDの3手法を敵対的レビュー（Adversarial Review）でつなぐ開発手法VSDD。本ワークフローの検証ゲート設計の思想的土台 |

参考: [SDD + TDD + VDD を融合した Claude Code プラグイン「VSDD Claude Code」を作った話](https://zenn.dev/sc30gsw/articles/1373752d9713b3)（Zenn）

## 背景 — なぜ仕様駆動 + 検証が必要か

LLM が生成したコードは、テストを通過しレビューでも問題が見つからないのに、リリース後に仕様との乖離やエッジケースの欠落が露呈することがあります。表面上は正しく見えながら隠れた欠陥を抱えたコード — いわゆる **AI スロップ（AI slop）** です。

対策は、AI モデル単体に委ねるのではなく、計画・実装・レビューといったフェーズを構造的に強制する**ハーネス（制御基盤）**を設計することです。仕様書を書いても AI がそれを忠実に守る保証はありません。「仕様に合っているように見えるコード」ではなく「本当に仕様を満たしているコード」だけを完了と認める仕組みが必要です。

### VSDD とは

**VSDD（Verified Spec-Driven Development）** は、3 つの開発手法と 1 つのゲートを統合したワークフローです。

| 要素 | 内容 |
| --- | --- |
| **SDD**（仕様駆動開発） | コードを書く前に仕様を完全に定義する。入力・出力・エッジケース・エラー条件を明文化してから実装に進む |
| **TDD**（テスト駆動開発) | 失敗するテストを書いてからでないと実装コードに触れられない。Red → Green → Refactor を機械的に強制 |
| **VDD**（検証駆動開発） | テストをパスしただけでは完了にしない。批判的なレビューが欠陥を掘り起こし、何も見つからなくなって初めて完了 |
| **敵対的レビュー** | 実装者とコンテキストを共有しない別エージェントが、ディスク上の成果物だけを読んで判定を下す |

「完了」の定義を「テストが通った」から「**仕様・テスト・実装・検証** の 4 条件を満たした」に拡張するのが VSDD の核心です。

参考:

- [SDD + TDD + VDD を融合した Claude Code プラグイン「VSDD Claude Code」を作った話](https://zenn.dev/sc30gsw/articles/1373752d9713b3)（Zenn）
- [VSDD 原典](https://gist.github.com/dollspace-gay/d8d3bc3ecf4188df049d7a4726bb2a00)（gist）
- [Harness design for long-running apps](https://www.anthropic.com/engineering/harness-design-long-running-apps)（Anthropic）

### このリポジトリでの VSDD 実装

| VSDD 要素 | 本ワークフローでの実装 |
| --- | --- |
| VSDD | EARS 形式の要件定義（Phase 2）→ 設計（Phase 4）→ タスク分解（Phase 5）。`_steering/` でコードベース基準・ドメイン用語を強制 |
| TDD | Phase 7のSonnet `ultracode` Dynamic Workflowが`tasks.md`全体を読み、依存関係・並列化・worktreeを判断してRed → Green → Refactorを実行 |
| VDD / 検証ゲート | Phase 3（要件）・Phase 6（REQ→Design→TASK）・Phase 7（実装workflow計画）・Phase 8（コード／セキュリティ）の全レビューをOpus `xhigh`で実施 |
| 独立レビュー | 作成workerと会話コンテキストを共有しない新規Opus agentが、ディスク上の成果物と対象commitだけを審査。コードとセキュリティも別agent |
| トレーサビリティ | `REQ-NNN` → `TASK-NNN` → `feat(TASK-NNN):` コミット → PR テーブルの連鎖。「このコードはなぜ存在するか」を要件まで遡れる |
| 検証ゲート | 構造化された`verdict`だけで自動遷移。CRITICAL/HIGHは必ず停止し、各上流レビューは最大3回、実装後レビューは最大2回の修正まで |

```
Project Steering（コードベース基準）
    ↓ /vsdd-steering
仕様ソース（Notion ページ / 手元の要件メモ）
    ↓ /vsdd-init
source-notion.md / source-request.md
    ↓ /vsdd-requirements
requirements.md   (REQ-001..N — EARS 形式)
    ↓ Opus Requirements Review
    ↓ /vsdd-design
design.md         (Mermaid 図 + ファイル構造)
    ↓ /vsdd-tasks
tasks.md          (TASK-001..M)
    ↓ Opus Plan Review
    ↓ /vsdd-impl
implementation-workflow.md
    ↓ Opus Workflow Review
コード + テスト   (Sonnet Dynamic Workflow、TDD、TASK ごとにコミット)
implementation-ledger.md (TDD証跡 + TASK→commit)
    ↓ 別々の Opus Code / Security Review
    ↓ managed Phase 9 (`resume <slug> --until pr`)
GitHub PR         (REQ → TASK → commit トレーサビリティ表付き)
```

### スタック非依存設計 — tech.md が唯一のスタック知識源

本プラグインのskill群はプロセス（フェーズ・検証ゲート・トレーサビリティ）のみを定義し、技術スタック固有の知識をハードコードしません。スタック知識は`/vsdd-steering`が検出・確認して生成する`.claude/specs/_steering/tech.md`に集約され、各skillが実行時に読み込みます。

| tech.md 節 | 内容 | 消費する skill |
| --- | --- | --- |
| §1 Stack | 技術スタック表（マニフェスト検出 + 対話確認） | vsdd-design（`/ecc:plan` プロンプト組立）・レビュー系（docs-lookup 対象） |
| §2 Design Viewpoints | design.md が必ずカバーすべき設計観点 | vsdd-design（観点セクション生成）・vsdd-review-plan（Check I: 観点カバレッジ検証） |
| §3 Conventions | エラー処理・バリデーション等の実装規約 | vsdd-impl（コミット時強制）・vsdd-review（プロジェクト層チェック） |
| §4 Verification Commands | lint / format / type check / test の実コマンド | vsdd-impl（TDD サイクル）・vsdd-review |

これによりフロントエンド・バックエンド API・フルスタック・CLI などプロジェクト種別を問わず同一ワークフローが機能します。観点の候補一覧は [design-viewpoints カタログ](skills/vsdd-steering/references/design-viewpoints.md) を参照してください。

## ドキュメント

| ドキュメント | 内容 |
| --- | --- |
| [vsdd-workflow.md](docs/vsdd-workflow.md) | 概念ガイド — 解決する問題、10フェーズ、モデルルーティング、トレーサビリティ、検証ゲート |
| [vsdd-workflow-usage.md](docs/vsdd-workflow-usage.md) | Usage Guide — 初回セットアップ（steering bootstrap、Open Question 解消）から日次運用まで |
| [vsdd-workflow-skills.md](docs/vsdd-workflow-skills.md) | Skills Detail — 各 Skill の入出力・引数・呼出エージェントのリファレンス |

## フェーズ一覧

| #   | フェーズ         | コマンド                                 | 主な成果物                                             |
| --- | ---------------- | ---------------------------------------- | ------------------------------------------------------ |
| 0   | **Steering**     | `/vsdd-steering [--force] [--dry-run]`    | `_steering/{tech,structure,context,open-questions}.md` |
| 1   | **Init**         | `/vsdd-init <slug> [source] [--mode]`      | `source-notion.md` または `source-request.md`, `progress.md` |
| 2   | **Requirements** | `/vsdd-requirements <slug>`               | `requirements.md`（EARS 形式 REQ-001..N）              |
| 3   | **Review Req**   | `/vsdd-review-requirements <slug>`        | `review-results/requirement-review.md`                 |
| 4   | **Design**       | `/vsdd-design <slug>`                     | `design.md`                                            |
| 5   | **Tasks**        | `/vsdd-tasks <slug>`                      | `tasks.md`, `progress.md` 更新                         |
| 6   | **Review Plan**  | `/vsdd-review-plan <slug>`                | `review-results/plan-review.md`                        |
| 7   | **Implement**    | `/vsdd-impl <slug>`                       | immutable workflow + `implementation-ledger.md` + コード + テスト + TASK commit |
| 8   | **Reviews**      | `/vsdd-review <slug>`                     | `review-results/{code-review,security-review}.md`      |
| 9   | **PR**           | `/vsdd-run ... --until pr`                | broker検証済みGitHub PR                                |
| -   | **Orchestrator** | `/vsdd-run start|resume|status|cancel|cleanup ...` | Phase 0〜9をモデル固定・検証付きで自動実行・再開 |
| -   | **Meta**         | `/vsdd-workflow [slug]`                   | フェーズ状態の表示（読み取り専用）                     |

成果物はすべて `.claude/specs/<slug>/` 以下に保存されます。

仕様ソースは Notion ページ URL でも、手元の要件メモでも構いません。Notionは`source-notion.md`、ファイルまたは詳細briefは`source-request.md`として保存され、以降のフェーズの真実の源になります。

## インストール

```bash
/plugin marketplace add sc30gsw/ecc-vsdd
/plugin install ecc-vsdd@ecc-vsdd
/reload-plugins
```

marketplace内の`ecc` entryは`affaan-m/ECC`を明示的なHTTPS Git sourceとして参照し、`ecc-vsdd`のplugin manifestが`dependencies: ["ecc"]`で依存を宣言します。`ecc-vsdd`のインストール時にECCも自動解決されるため、`.claude/settings.json`の`enabledPlugins`やECCの個別installは不要です。インストール後、スキルは `/ecc-vsdd:vsdd-init` のように名前空間付きで呼べます（他プラグインと重複しなければ `/vsdd-init` の短縮形も可）。

ルートの`agents/`、`skills/`、`hooks/`、`scripts/`はプラグイン本体に同梱されます。したがってインストール後は15個のVSDD専用agentも利用可能で、別途`agents/`をコピーする必要はありません。

## クイックスタート — 全自動

Fableを制御専用agentとして起動し、`start`を1回実行します。Steeringは未作成またはstaleの場合だけOpusが自動更新します。

```bash
# プラグイン導入後、Fable highの制御専用セッションを起動
claude --agent ecc-vsdd:vsdd-orchestrator --effort high

# Claude Code内: 要件ソースからPRまで自動実行
/ecc-vsdd:vsdd-run start mail-groups-filter https://www.notion.so/xxxx --mode auto --until pr

# 中断・失敗後
/ecc-vsdd:vsdd-run resume mail-groups-filter

# Review完了後、明示的にPRまで延長
/ecc-vsdd:vsdd-run resume mail-groups-filter --until pr

# 再開時に仕様ソースを追加・差し替える場合（Requirements以降を自動無効化）
/ecc-vsdd:vsdd-run resume mail-groups-filter https://www.notion.so/yyyy

# 状態確認・安全な停止・明示的な後片付け
/ecc-vsdd:vsdd-run status mail-groups-filter
/ecc-vsdd:vsdd-run cancel mail-groups-filter
/ecc-vsdd:vsdd-run cleanup mail-groups-filter
```

Fableは成果物・コード・テスト・レビュー・PR本文を書きません。SkillスコープのhookがFableのWrite/Edit、任意Bash、未固定agent起動、呼出し時のmodel overrideを拒否し、各工程を次のモデルへ強制ルーティングします。`vsdd-run`のstrict hookは検証済みorchestratorのsession IDとcwdを、ユーザー専用OS runtime directory（directory `0700`、record `0600`、7日TTL）へ記録します。同じsession ID・cwd・subagent IDを持ち、agent定義・model・effortの検証を通過したpinned workerだけにglobal hookがClaude Codeの`permissionDecision: allow`を返し、`SessionEnd`でrecordを削除します。Skill hookでは利用できない`${CLAUDE_PLUGIN_DATA}`に依存しないため、plugin agentへ同梱できない`permissionMode`やproject permission設定なしで無人実行できます。直接起動worker・別session・別cwd・strict認可前のglobal hookは自動承認されません。Claude Codeのsubagent hook payloadには実modelが含まれず、バージョンによっては実effortも省略されるため、guardは親Fableの値をsubagentへ誤適用しません。代わりに起動前override拒否と配布agent frontmatterを必ず検査し、payloadにeffortがある場合は実効値も照合します。独立main sessionは自身のpayloadに含まれるmodelを検証し、effortを必須検証します。

| 工程 | モデル | effort |
| --- | --- | --- |
| Orchestrator | Fable | `high` |
| Steering / Requirements / Design | Opus | `xhigh` |
| 全レビュー | 新規Opus | `xhigh` |
| Init / Status / lifecycle | Haiku | `low` |
| Tasks | Sonnet | `high` |
| Implementation | Sonnet Dynamic Workflow | `ultracode` |
| 通常のレビュー修正 | Sonnet | `high` |
| 複雑なレビュー修正 | Sonnet Dynamic Workflow | `ultracode` |
| PR | Sonnet | `medium` |

`inherit`、fallback model、`max`、workerとしてのFableは使用しません。必要なモデル・effort・Dynamic Workflowが利用できない場合は`VSDD RUN BLOCKED`で停止します。

| オプション | デフォルト | 内容 |
| --- | --- | --- |
| `--mode auto\|standard` | `auto` | 新規specの表示・対話モード。モデルと検証範囲は変わらない |
| `--base <ref>` | detected repository default | `origin/HEAD`等から検出したcleanな統合ブランチの起点。曖昧なら停止 |
| `--until review\|pr` | `review` | 独立レビューまで / GitHub PR作成まで。PRには明示的な`pr`が必要 |

完全な無人実行には、Notion URL、既存ソース、または詳細な機能説明が必要です。`execution_mode: unattended`はRequirements内の7項目を含む全フェーズの質問・確認・上書き確認を無効にし、保存済みソースとリポジトリ証拠から回答を導出します。可逆な技術的仮定は記録して続行しますが、製品仕様・データ損失・セキュリティ・互換性・破壊的操作・外部権限に関する未決事項は自動推測せず停止します。

Startは`operation: bootstrap`を明示し、同梱runtimeの専用`bootstrap` commandで最初に`vsdd/<slug>` worktreeと`run-state.json`だけを作ります。この操作だけはPhase 0より前なのでSteeringを要求せず、そこで終了します。その後のSteeringと`operation: phase`のInitが正確なskeletonだけを消費します。既存worktreeとの衝突と、自分で作ったbootstrapの取り違えを機械的に区別します。

各フェーズ前には同梱runtimeが成果物hash、必須の前段phase、構造化review snapshot、SteeringのOpen/DRAFT、固定`vsdd/<slug>` branch、TASK集合を再検証します。上流成果物を正規再生成してsnapshotした場合も、新しい現在phaseだけを完了に保ち、依存する旧review・設計・TASK・実装を無効化します。TASK commitはintegration `HEAD`のancestorでなければならず、Code/Security reviewは現在のfull SHAに一致し、同一の現行review attemptで作成されたOpus PASSでなければPRへ進めません。

Phase 7は`tasks.md`全体を読むSonnet `ultracode`セッションです。launcher自身がdeterministic preflight、phase状態、保存済みsession IDを確認し、plugin manifest依存もisolated childへ明示的に引き継いでからClaudeを起動します。長時間処理はlauncher-owned detached supervisorが所有し、Fableはshell backgroundを使わず45秒単位のforeground `wait`をterminal結果まで繰り返します。これによりBashの10分上限、Fable compaction、session再開を跨いでもchildが失われません。専用sessionとWorkflow agentは無人実行用の読取tool権限を持ち、`.claude/specs`はRead/Glob/Grepで参照し、background Workflowの完了通知と成果物検証が終わるまで最終結果を返しません。各stageは現在の`workflow_run_id`を返し、plan/revise-planでは新しい内容と同じrun IDを本文へ保存するため、既存planを読んだだけのstale COMPLETEや古いrun IDの流用はlauncherが拒否します。Dynamic WorkflowがTASK依存関係、並列化、worktree、統合順を判断して`implementation-workflow.md`へ保存し、新規OpusのPASS後だけ実装へ進みます。承認済みworkflowは変更せず、attempt・TDD証跡・`TASK-to-SHA Mapping`は`implementation-ledger.md`へ追記し、完了TASKを`progress.md`の`done`へ同期します。実装・修正stageの最終`COMPLETE`は、launcherが同梱runtimeの`task-gate`を実行し、TASK集合、`done`状態、attempt PASS、Markdown形式のSHA mapping、commit存在性とintegration `HEAD`到達性のすべてが`READY`になった場合だけ受理します。review roundとTASK attemptは`run-state.json`の永続ledgerで開始・完了を数え、3回目のREVISE/FAIL時点で機械的にBLOCKEDになります。`ultracode`はxhigh推論と自動Workflow orchestrationを組み合わせるClaude Code設定です。詳細は[公式ドキュメント](https://code.claude.com/docs/ja/workflows#have-claude-write-a-workflow)を参照してください。

Phase 9はworkerの完了メッセージだけでは完了しません。`UserPromptSubmit` hookは、現在の1行の`start|resume ... --until pr`だけをsession ID・canonical cwd・prompt IDへ結び付け、次のユーザープロンプトで消去します。strict hookはその同意をPR worker起動時に一度だけ消費し、`VSDD_RUN_CONTEXT`とruntime preflightを検証します。`SubagentStart`はランダムcapabilityを実際のPR worker agent IDへ結び付けます。guardが観測できる直接commandと一般的なshell/interpreter wrapperでは、全workerの`git push`、`git send-pack`、`gh pr`/`gh api`変更操作を拒否します。PR workerは`pr-body.md`だけを作り、専用brokerが認可とpreflight、remote base、正確なintegration refを再検証してpush/PR作成・GitHub identity検証・`pr-result.json`保存を行います。current integration `HEAD`と一致するruntime snapshotが成功した場合だけPR phaseを完了にします。

このhook防御は、Claude Codeが観測する通常のtool commandに対する事故防止・contract enforcementです。悪意あるworkerに対するsecurity boundaryではなく、任意の実行ファイルや難読化されたスクリプト内部までOSレベルでnetworkを遮断しません。信頼できないworker/toolを同じホストで動かす場合は、GitHub資格情報を持たせないsandbox、送信network policy、保護branch、GitHub ruleset、最小権限tokenを実際のsecurity boundaryとして併用してください。

ReviewまたはPRの証拠が揃った後も、同梱runtimeの`complete --reached review|pr`が成功するまでtop-level runは完了しません。このterminal gateが`status: COMPLETE`、`reached`、terminal `current_phase`、`completed_at`を原子的に保存します。Review完了後にPRまで進める場合は、ユーザーが明示した`resume <slug> --until pr`だけを受け付け、`extend --until pr`で外部操作境界を記録してから再開します。

### Publication-ready判定

unit/integration test、subprocessを含む全`scripts/*.py`それぞれのline coverage 80%以上、Python/JSON検証、`claude plugin validate --strict`、別々のOpus `xhigh` code/security release reviewに加え、新規marketplace installした同一RC artifactでexact `start ... --until pr`のReview・broker経由PR到達と、同意なし拒否の2つのE2Eを完走した時点をpublication-readyとします。Opus reviewのP0/P1判定は上記threat model内の通常・低コストな迂回を対象とし、OS sandboxでしか防げない任意binary内部の難読化をhook実装のrelease blockerにはしません。mock payload、dry-run、`--plugin-dir`だけでは公開可と判定しません。

## クイックスタート — フェーズを個別実行

```bash
# 1. ステアリングをbootstrap（Opus xhigh。stale時のみ再実行）
/vsdd-steering

# 2. Open Questions を解消（grill or dismiss）
/grill-with-docs .claude/specs/_steering/open-questions.md の Open 全件を順に解消したい

# 3. spec を初期化（仕様ソースが Notion にある場合は URL を渡す）
/vsdd-init mail-groups-filter https://www.notion.so/xxxx

# 4. フェーズ2〜9を順に実行（直接実行でも各専用workerへ委譲）
/vsdd-requirements mail-groups-filter
/vsdd-review-requirements mail-groups-filter
/vsdd-design mail-groups-filter
/vsdd-tasks mail-groups-filter
/vsdd-review-plan mail-groups-filter
/vsdd-impl mail-groups-filter
/vsdd-review mail-groups-filter
# PR publicationはmanaged runのexact promptだけで許可
/ecc-vsdd:vsdd-run resume mail-groups-filter --until pr

# 中断後の再開: 状態確認してから続きを実行
/vsdd-workflow mail-groups-filter
```

## モード

`/vsdd-init <slug> [--mode standard|auto]` で一度だけ指定（省略時は `standard`）。

| モード | 想定ユーザー | 特徴 |
| --- | --- | --- |
| **`standard`** | エンジニア | 個別Phaseで説明を詳しく表示。モデルルーティングと検証ゲートはautoと同じ |
| **`auto`** | 非エンジニア / AI に任せたいエンジニア | 自動実行向けの簡潔な表示。重大な未決事項だけ停止 |

実行例は[Usage Guide](docs/vsdd-workflow-usage.md)を参照してください。

## リポジトリ構成

```
.claude-plugin/
├── plugin.json           # プラグインマニフェスト
└── marketplace.json      # マーケットプレイス定義（/plugin marketplace add 用）

agents/                   # model / effort固定のVSDD専用agent
├── vsdd-orchestrator.md  # Fable high（制御専用）
├── vsdd-implementation-driver.md # Sonnet ultracode用
└── vsdd-*-reviewer.md    # 新規Opus xhighレビュー群

scripts/
├── vsdd-model-guard.py   # Fableの作業・任意tool・model overrideを機械的に拒否
├── vsdd-launch-worker.py # 独立Sonnet Dynamic Workflowセッション起動
└── vsdd-runtime-state.py # bootstrap/base/hash/phase/review/TASK/commit遷移gate

skills/                   # プラグインスキル本体（自動検出）
├── vsdd-steering/         # Phase 0: ステアリング bootstrap / refresh
│   ├── templates/tech.md                # tech.md 空テンプレート（4 節構造）
│   └── references/design-viewpoints.md  # 設計観点カタログ（プロジェクト種別ごと）
├── vsdd-init/             # Phase 1: spec ディレクトリ初期化
├── vsdd-requirements/     # Phase 2: EARS 形式の要件定義
├── vsdd-review-requirements/  # Phase 3: 要件レビュー（検証ゲート）
├── vsdd-design/           # Phase 4: 設計（Mermaid + ファイル構造）
├── vsdd-tasks/            # Phase 5: TDD 順のタスク分解
├── vsdd-review-plan/      # Phase 6: トレーサビリティ検証（検証ゲート）
├── vsdd-impl/             # Phase 7: Sonnet Dynamic Workflow + TDD
├── vsdd-review/           # Phase 8: 別々のOpusコード／セキュリティレビュー
├── vsdd-pr/               # Phase 9: GitHub PR 作成
├── vsdd-run/              # Orchestrator: Phase 0〜9の自動実行・再開・状態契約
├── vsdd-workflow/         # Meta: フェーズ進捗ダッシュボード
├── git-pr/               # PR 作成補助
├── grill-me/             # 計画を問い詰めるインタビュー型スキル（外部由来）
└── grill-with-docs/      # ドメイン用語 / ADR を整合させる grill スキル（外部由来）

.agents/skills/           # 外部由来スキルのソース（mattpocock/skills、skills-lock.json で管理）
docs/        # ドキュメント（上記参照）
skills-lock.json          # 外部スキルのソース / ハッシュ管理
```

## トレーサビリティ規約

VSDD の核心は「このコードはなぜ存在するか」を仕様要件まで遡れることです。

| 成果物   | 形式                       | 例                                          |
| -------- | -------------------------- | ------------------------------------------- |
| 要件     | `REQ-NNN`                  | `REQ-001`                                   |
| タスク   | `TASK-NNN`                 | `TASK-001`                                  |
| コミット | `feat/fix(TASK-NNN): 説明` | `feat(TASK-003): URLクエリ状態フックを追加` |

```
REQ-001（要件） → design.md §3.2（設計） → TASK-001（タスク）
  → feat(TASK-001): コミット → PR トレーサビリティテーブル
```

Phase 6ではREQ → 設計 → タスクの連鎖を9項目（観点カバレッジ含む）で機械検証し、いずれか❌なら実装をブロックします。詳細は[Workflow Guide](docs/vsdd-workflow.md)を参照してください。

## 前提

- [Claude Code](https://claude.com/claude-code) 2.1.203以上
- macOSまたはLinux（Windows nativeはprivate-record防御を同等条件で検証できるまで未対応。WSLはLinuxとして扱う）
- Python 3.10以上
- Dynamic Workflowsを利用できるClaude Codeプラン／API設定
- ECC プラグイン（`ecc:plan` / `ecc:tdd-workflow` / `ecc:code-review` 等のスキル・エージェントを利用）
- `gh` CLI（Phase 9 の PR 作成に使用）
- Notion 連携（任意 — 仕様ソースが Notion にある場合のみ）

## ライセンス

[MIT License](LICENSE)
