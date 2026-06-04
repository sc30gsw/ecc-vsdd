# ecc-vsdd — VSDD 思想に基づく仕様駆動開発ワークフロー

**仕様（spec）を唯一の真実の源**として、要件定義 → 設計 → タスク分解 → TDD 実装 → 検証 → PR を **9 フェーズ + 厳格な承認ゲート**で機械的に強制する Claude Code プラグインです。

VSDD（Verified Spec-Driven Development）の思想を、ECC プラグインのスキル・エージェント群の上に実装しています。

## 名前の由来

**ecc-vsdd** = **ecc**（everything-claude-code）+ **VSDD**（Verified Spec-Driven Development）

| 要素 | 由来 |
| --- | --- |
| **ecc** | [everything-claude-code](https://github.com/affaan-m/ECC)（現 ECC）。本ワークフローは ECC プラグインのスキル・エージェント（`ecc:plan` / `ecc:tdd-workflow` / `ecc:code-review` 等）を実行基盤として利用している |
| **VSDD** | SDD・TDD・VDD の 3 手法を敵対的レビュー（Adversarial Review）でつなぐ開発手法 VSDD。本ワークフローの承認ゲート・検証フェーズ設計の思想的土台 |

参考: [SDD + TDD + VDD を融合した Claude Code プラグイン「VSDD Claude Code」を作った話](https://zenn.dev/sc30gsw/articles/1373752d9713b3)（Zenn）

## 背景 — なぜ仕様駆動 + 検証が必要か

LLM が生成したコードは、テストを通過しレビューでも問題が見つからないのに、リリース後に仕様との乖離やエッジケースの欠落が露呈することがあります。表面上は正しく見えながら隠れた欠陥を抱えたコード — いわゆる **AI スロップ（AI slop）** です。

対策は、AI モデル単体に委ねるのではなく、計画・実装・レビューといったフェーズを構造的に強制する**ハーネス（制御基盤）**を設計することです。仕様書を書いても AI がそれを忠実に守る保証はありません。「仕様に合っているように見えるコード」ではなく「本当に仕様を満たしているコード」だけを完了と認める仕組みが必要です。

### VSDD とは

**VSDD（Verified Spec-Driven Development）** は、3 つの開発手法と 1 つのゲートを統合したワークフローです。

| 要素 | 内容 |
| --- | --- |
| **VSDD**（仕様駆動開発） | コードを書く前に仕様を完全に定義する。入力・出力・エッジケース・エラー条件を明文化してから実装に進む |
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
| TDD | Phase 7 で `ecc:tdd-workflow` による Red → Green → Refactor。テストなしの実装コミットは不可 |
| VDD / 検証ゲート | Phase 3（要件レビュー）・Phase 6（トレーサビリティ検証 — 9 チェックいずれか ❌ で実装ブロック）・Phase 8（コード + セキュリティレビュー — CRITICAL 0 件まで PR 不可） |
| 独立レビュー | 各レビューフェーズで `requirements-analyst` / `ecc:planner` / `ecc:architect` / `ecc:security-review` 等の独立エージェントが成果物を審査 |
| トレーサビリティ | `REQ-NNN` → `TASK-NNN` → `feat(TASK-NNN):` コミット → PR テーブルの連鎖。「このコードはなぜ存在するか」を要件まで遡れる |
| 承認ゲート | 全フェーズ末尾で `CONFIRM` 入力を要求。人間が各成果物を承認するまで次へ進めない |

```
Project Steering（コードベース基準）
    ↓ /vsdd-steering
仕様ソース（Notion ページ / 手元の要件メモ）
    ↓ /vsdd-init
source-notion.md
    ↓ /vsdd-requirements
requirements.md   (REQ-001..N — EARS 形式)
    ↓ /vsdd-design
design.md         (Mermaid 図 + ファイル構造)
    ↓ /vsdd-tasks
tasks.md          (TASK-001..M)
    ↓ /vsdd-impl
コード + テスト   (TDD、TASK ごとにコミット)
    ↓ /vsdd-pr
GitHub PR         (REQ → TASK → commit トレーサビリティ表付き)
```

### スタック非依存設計 — tech.md が唯一のスタック知識源

本プラグインの skill 群はプロセス（フェーズ・承認ゲート・トレーサビリティ）のみを定義し、技術スタック固有の知識をハードコードしません。スタック知識は `/vsdd-steering` が検出 + 対話確認で生成する `.claude/specs/_steering/tech.md` に集約され、各 skill が実行時に読み込みます。

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
| [vsdd-workflow.md](docs/vsdd-workflow.md) | 概念ガイド — 解決する問題、9 フェーズ、トレーサビリティ規約、承認ゲート、トラブルシュート |
| [vsdd-workflow-usage.md](docs/vsdd-workflow-usage.md) | Usage Guide — 初回セットアップ（steering bootstrap、Open Question 解消）から日次運用まで |
| [vsdd-workflow-skills.md](docs-workflow/vsdd-workflow-skills.md) | Skills Detail — 各 Skill の入出力・引数・呼出エージェントのリファレンス |

## フェーズ一覧

| #   | フェーズ         | コマンド                                 | 主な成果物                                             |
| --- | ---------------- | ---------------------------------------- | ------------------------------------------------------ |
| 0   | **Steering**     | `/vsdd-steering [--force] [--dry-run]`    | `_steering/{tech,structure,context,open-questions}.md` |
| 1   | **Init**         | `/vsdd-init <slug> [notion-url] [--mode]` | `source-notion.md`, `progress.md`                      |
| 2   | **Requirements** | `/vsdd-requirements <slug>`               | `requirements.md`（EARS 形式 REQ-001..N）              |
| 3   | **Review Req**   | `/vsdd-review-requirements <slug>`        | `review-results/requirement-review.md`                 |
| 4   | **Design**       | `/vsdd-design <slug>`                     | `design.md`                                            |
| 5   | **Tasks**        | `/vsdd-tasks <slug>`                      | `tasks.md`, `progress.md` 更新                         |
| 6   | **Review Plan**  | `/vsdd-review-plan <slug>`                | `review-results/plan-review.md`                        |
| 7   | **Implement**    | `/vsdd-impl <slug> [task-id]`             | コード + テスト（TDD、`feat(TASK-NNN):` コミット）     |
| 8   | **Code Review**  | `/vsdd-review <slug>`                     | `review-results/code-review.md`                        |
| 9   | **PR**           | `/vsdd-pr <slug>`                         | GitHub PR                                              |
| -   | **Meta**         | `/vsdd-workflow [slug]`                   | フェーズ状態の表示（読み取り専用）                     |

成果物はすべて `.claude/specs/<slug>/` 以下に保存されます。

仕様ソースは Notion ページ URL でも、手元の要件メモでも構いません（`/VSDD-init` の Notion URL は任意）。いずれの場合も `source-notion.md` として保存され、以降のフェーズの真実の源になります。

## インストール

```bash
/plugin marketplace add sc30gsw/ecc-vsdd
/plugin install ecc-vsdd@ecc-vsdd
/reload-plugins
```

インストール後、スキルは `/ecc-vsdd:vsdd-init` のように名前空間付きで呼べます（他プラグインと重複しなければ `/vsdd-init` の短縮形も可）。

## クイックスタート

```bash
# 1. ステアリングを bootstrap（初回のみ・以降は /vsdd-init が自動呼出）
/vsdd-steering

# 2. Open Questions を解消（grill or dismiss）
/grill-with-docs .claude/specs/_steering/open-questions.md の Open 全件を順に解消したい

# 3. spec を初期化（仕様ソースが Notion にある場合は URL を渡す）
/vsdd-init mail-groups-filter https://www.notion.so/xxxx

# 4. フェーズ 2〜9 を順に実行（各フェーズ完了時に CONFIRM ゲート）
/vsdd-requirements mail-groups-filter
/vsdd-review-requirements mail-groups-filter
/vsdd-design mail-groups-filter
/vsdd-tasks mail-groups-filter
/vsdd-review-plan mail-groups-filter
/vsdd-impl mail-groups-filter
/vsdd-review mail-groups-filter
/vsdd-pr mail-groups-filter

# 中断後の再開: 状態確認してから続きを実行
/vsdd-workflow mail-groups-filter
```

## モード

`/vsdd-init <slug> [--mode standard|auto]` で一度だけ指定（省略時は `standard`）。

| モード | 想定ユーザー | 特徴 |
| --- | --- | --- |
| **`standard`** | エンジニア | 人間が意思決定。各フェーズと TDD サイクルで確認しながら進める |
| **`auto`** | 非エンジニア / AI に任せたいエンジニア | AI が草案・実装まで進める。承認は重要ゲート（フェーズ 3, 6, 8）に集中 |

詳細比較は [vsdd-workflow.md §4](docs/vsdd-workflow.md#4---mode-standard-と---mode-auto-の違い) を参照。

## リポジトリ構成

```
.claude-plugin/
├── plugin.json           # プラグインマニフェスト
└── marketplace.json      # マーケットプレイス定義（/plugin marketplace add 用）

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
├── vsdd-impl/             # Phase 7: TDD 実装（Red → Green → Refactor）
├── vsdd-review/           # Phase 8: コード + セキュリティレビュー（検証ゲート）
├── vsdd-pr/               # Phase 9: GitHub PR 作成
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

Phase 6 では REQ → 設計 → タスクの連鎖を 9 項目（観点カバレッジ含む）で機械検証し、いずれか ❌ なら実装をブロックします。詳細は [vsdd-workflow.md §5](docs/vsdd-workflow.md#5-トレーサビリティ規約) を参照。

## 前提

- [Claude Code](https://claude.com/claude-code)
- ECC プラグイン（`ecc:plan` / `ecc:tdd-workflow` / `ecc:code-review` 等のスキル・エージェントを利用）
- `gh` CLI（Phase 9 の PR 作成に使用）
- Notion 連携（任意 — 仕様ソースが Notion にある場合のみ）
