# VSDD ワークフロー — Verified Spec-Driven Development ガイド

> **対象読者**: エンジニア・非エンジニアを問わず、AI アシスタントと協力して
> 仕様（spec）を唯一の真実の源に、要件定義から Pull Request まで一気通貫で進めたい方

---

## 1. このワークフローが解決すること

### 問題定義

通常の開発では、以下のようなギャップが発生しがちです。

| 状態                                  | 問題                                                         |
| ------------------------------------- | ------------------------------------------------------------ |
| 仕様メモ・チケットがある（Notion 等） | 要件が自然言語で書かれており曖昧。実装者によって解釈が異なる |
| 実装に入った                          | 何を作ったか・なぜこう作ったかの根拠がコードに残らない       |
| レビュー・マージ後                    | 要件とコードの対応関係が失われ、後から追跡できない           |

さらに AI 開発では、**テストを通過しレビューでも問題が見つからないのに、リリース後に仕様との乖離やエッジケースの欠落が露呈する**コード — いわゆる **AI スロップ（AI slop）** — の問題が加わります。仕様書を書いても、AI がそれを忠実に守る保証はありません。

### 解決アプローチ — VSDD

**VSDD（Verified Spec-Driven Development）** は、SDD（仕様駆動開発）・TDD（テスト駆動開発）・VDD（検証駆動開発）の 3 手法を検証ゲートでつなぎ、「完了」の定義を「テストが通った」から「**仕様・テスト・実装・検証** の 4 条件を満たした」に拡張する開発手法です。本ワークフローはこれを **9 フェーズ + 厳格な承認ゲート** として実装します。

| VSDD 要素                 | 本ワークフローでの実装                                                                                                                              |
| ------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| **SDD**（仕様駆動開発）   | EARS 形式の要件定義（フェーズ 2）→ 設計（フェーズ 4）→ タスク分解（フェーズ 5）。`_steering/` でコードベース基準・ドメイン用語を強制                 |
| **TDD**（テスト駆動開発） | フェーズ 7 で `ecc:tdd-workflow` による Red → Green → Refactor。テストなしの実装コミットは不可                                                       |
| **VDD**（検証駆動開発）   | フェーズ 3（要件レビュー）・フェーズ 6（トレーサビリティ検証 — いずれか ❌ で実装ブロック）・フェーズ 8（CRITICAL 0 件まで PR 不可）の 3 検証ゲート |
| **独立レビュー**          | 各検証ゲートで `requirements-analyst` / `ecc:planner` / `ecc:architect` / `ecc:security-review` 等の独立エージェントが成果物を審査                   |
| **トレーサビリティ**      | REQ → TASK → commit → PR の連鎖（§5）。「このコードはなぜ存在するか」を要件まで遡れる                                                                |
| **承認ゲート**            | 各フェーズ末尾で `CONFIRM` 入力を要求（§6）。人間が成果物を承認するまで次へ進めない                                                                  |

参考: [VSDD 原典](https://gist.github.com/dollspace-gay/d8d3bc3ecf4188df049d7a4726bb2a00) / [VSDD Claude Code（Zenn）](https://zenn.dev/sc30gsw/articles/1373752d9713b3)

```
Project Steering（コードベース基準）
    ↓ /vsdd-steering  ← 自動 bootstrap / refresh、Open Question 検出
.claude/specs/_steering/{tech,structure,context,open-questions}.md
    ↓
仕様ソース（Notion ページ / 手元の要件メモ）
    ↓ /vsdd-init      ← Step 0 で /vsdd-steering を内部呼出、新規 Q-XXX があれば停止
source-notion.md  (仕様ソースをローカル保存)
    ↓ /vsdd-requirements
requirements.md   (REQ-001..N — EARS 形式の要件定義)
    ↓ /vsdd-design
design.md         (Mermaid 図 + ファイル構造)
    ↓ /vsdd-tasks
tasks.md          (TASK-001..M — 実装タスク一覧)
    ↓ /vsdd-impl
コード + テスト   (TASK-001 ごとにコミット)
    ↓ /vsdd-pr
GitHub PR         (REQ → TASK → commit のトレーサビリティテーブル付き)
```

---

## 2. 9 フェーズの概要

| #   | フェーズ         | コマンド                                 | 主な成果物                                             |
| --- | ---------------- | ---------------------------------------- | ------------------------------------------------------ |
| 0   | **Steering**     | `/vsdd-steering [--force] [--dry-run]`    | `_steering/{tech,structure,context,open-questions}.md` |
| 1   | **Init**         | `/vsdd-init <slug> [notion-url] [--mode]` | `source-notion.md`, `progress.md`                      |
| 2   | **Requirements** | `/vsdd-requirements <slug>`               | `requirements.md`                                      |
| 3   | **Review Req**   | `/vsdd-review-requirements <slug>`        | `review.md §Requirements Review`                       |
| 4   | **Design**       | `/vsdd-design <slug>`                     | `design.md`                                            |
| 5   | **Tasks**        | `/vsdd-tasks <slug>`                      | `tasks.md`, `progress.md` 更新                         |
| 6   | **Review Plan**  | `/vsdd-review-plan <slug>`                | `review.md §Plan Review + §Traceability`               |
| 7   | **Implement**    | `/vsdd-impl <slug> [task-id]`             | コード + テスト, `progress.md` 更新                    |
| 8   | **Code Review**  | `/vsdd-review <slug>`                     | `review.md §Code Review + §Security`                   |
| 9   | **PR**           | `/vsdd-pr <slug>`                         | GitHub PR                                              |
| -   | **Meta**         | `/vsdd-workflow [slug]`                   | フェーズ状態の表示（読み取り専用）                     |

すべての成果物は `.claude/specs/<slug>/` 以下に保存されます。

---

## 3. 各フェーズで使うコマンドと成果物

### VSDD Skill 一覧（各コマンドの役割）

VSDD は `.claude/skills/vsdd-*/` に定義されたスキル群です。モードは `/vsdd-init` で一度だけ指定し、以降は `progress.md` を参照します。

| Skill                      | フェーズ       | 説明                                                                                                                                                         | 主な成果物                                       |
| -------------------------- | -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------ |
| `/vsdd-steering`            | 0 Steering     | `package.json` と `src/features/` からステアリング 4 ファイルを自動生成/更新し、ドリフトを検出（用語衝突・未使用シンボル・version 不整合・責務不明 feature） | `.claude/specs/_steering/*.md`                   |
| `/vsdd-init`                | 1 Init         | `/vsdd-steering` を内部呼出し新規 Q-XXX が無いか確認 → spec ディレクトリを初期化。Notion を `source-notion.md` に保存し mode を `progress.md` に記録          | `source-notion.md`, `progress.md`                |
| `/vsdd-requirements`        | 2 Requirements | `source-notion.md` から EARS 形式の要件（REQ-001..N）を作成                                                                                                  | `requirements.md`                                |
| `/vsdd-review-requirements` | 3 Review Req   | 要件の曖昧さ・矛盾・受入基準をレビュー。`requirements-analyst` / `ecc:planner` / `ecc:architect` を起動                                                      | `review-results/requirement-review.md`           |
| `/vsdd-design`              | 4 Design       | Mermaid 図・ファイル構造・状態管理方針を含む設計書を作成（`/ecc:plan` に委譲）                                                                               | `design.md`                                      |
| `/vsdd-tasks`               | 5 Tasks        | 設計を TDD 順の TASK-001..M に分解し、REQ・設計セクションと紐付け。`progress.md` にタスクテーブルを追記                                                      | `tasks.md`, `progress.md` 更新                   |
| `/vsdd-review-plan`         | 6 Review Plan  | REQ→設計→タスクのトレーサビリティ 6 項目を検証。`ecc:docs-lookup` / `ecc:planner` / `ecc:architect` を起動                                                   | `review-results/plan-review.md`                  |
| `/vsdd-impl`                | 7 Implement    | `/ecc:tdd-workflow` でタスクごとに TDD 実装し `feat(TASK-NNN):` でコミット                                                                                   | コード・テスト, `progress.md` タスクテーブル更新 |
| `/vsdd-review`              | 8 Code Review  | `code-review` / `/ecc:code-review` / `/ecc:security-review` で差分をレビュー（自動修正なし）                                                                 | `review-results/code-review.md`                  |
| `/vsdd-pr`                  | 9 PR           | REQ→TASK→commit 表付きの GitHub PR を作成                                                                                                                    | GitHub PR                                        |
| `/vsdd-workflow`            | Meta           | フェーズ進捗の表示のみ（ファイルは変更しない）                                                                                                               | —                                                |

関連ドキュメント:

- [Usage Guide（使い方）](./vsdd-workflow-usage.md) — 初回セットアップから日次運用まで
- [Skills Detail（各 Skill の詳細）](./vsdd-workflow-skills.md) — Skill ごとの入出力・引数・呼び出しエージェント

### フェーズ 0 — Steering

```bash
# 初回 bootstrap または毎回の refresh
/vsdd-steering

# 既存ステアリングを完全に初期化
/vsdd-steering --force

# 差分プレビューのみ（書込まない）
/vsdd-steering --dry-run
```

`/vsdd-steering` は spec 作成前にコードベースの基準を確定するスキルです。

- `package.json` から `tech.md` を生成（技術スタック一覧）
- `src/features/` から `structure.md` を生成（feature インベントリ）
- ドメイン用語集 `context.md` を保持（手動レイヤー + LLM ドラフト）
- 用語衝突 / version 不整合 / 責務不明 feature を検出し `open-questions.md` に追記

`/vsdd-init` は内部でこのスキルを呼出し、新規 Open Question が検出された場合は中断します。

**成果物:**

```
.claude/specs/_steering/
├── tech.md            # package.json 派生（自動再生）
├── structure.md       # src/features/ 派生（自動再生 + 手動注釈）
├── context.md         # ドメイン用語集（手動 + DRAFT マーカー）
└── open-questions.md  # Open / Resolved の 2 セクション
```

ADR は `docs/adr/NNNN-<slug>.md` に別建てで手書きします（このスキルは ADR を作成しません）。

---

### フェーズ 1 — Init

```bash
# Notion URL を渡す場合（推奨）
/vsdd-init mail-groups-filter https://www.notion.so/<workspace>/xxxx

# ローカルにメモがある場合（Notion URL なし）
/vsdd-init mail-groups-filter

# 自動モードで開始
/vsdd-init mail-groups-filter https://... --mode auto
```

**成果物:**

```
.claude/specs/mail-groups-filter/
├── source-notion.md   # Notion の内容（または手動入力した要件メモ）
└── progress.md        # フェーズ進捗トラッカー（自動管理）
```

`source-notion.md` は仕様ソース（Notion の内容または手動入力した要件メモ）をそのまま保存したもので、以降のフェーズで唯一の真実の源として AI が参照します。

---

### フェーズ 2 — Requirements

```bash
/vsdd-requirements mail-groups-filter
```

AI が `source-notion.md` を読み込み、EARS（Easy Approach to Requirements Syntax）形式で要件を構造化します。

**成果物:** `requirements.md`

```markdown
# Requirements: Mail Groups Filter

## REQ-001

**タイトル**: 名前によるフィルタリング
**EARS**: WHEN ユーザーが名前フィールドに文字を入力した場合、
システムは一致するメールグループのみを表示しなければならない
**受入基準**:

- [ ] 部分一致で検索される
- [ ] 大文字・小文字を区別しない
- [ ] 検索結果が 0 件の場合は「該当なし」と表示される

## REQ-002

...
```

**承認ゲート後**: `CONFIRM vsdd-review-requirements` と入力

---

### フェーズ 3 — Review Requirements

```bash
/vsdd-review-requirements mail-groups-filter
```

`requirements-analyst` エージェントが要件を検証します。

- 曖昧な表現の指摘
- 矛盾・重複の検出
- 受入基準の十分性チェック
- standard モードでは `ecc:docs-lookup`（スタックドキュメント収集）と `ecc:architect`（技術的実現可能性判定）も起動

**成果物:** `review-results/requirement-review.md`

---

### フェーズ 4 — Design

```bash
/vsdd-design mail-groups-filter
```

`/ecc:plan` スキルが設計を作成します。

**成果物:** `design.md`

```markdown
# Design: Mail Groups Filter

## 3.1 コンポーネント図

\`\`\`mermaid
graph LR
A[MailGroupsFilterForm] --> B[useMailGroupsQueryState]
B --> C[nuqs URLパラメータ]
A --> D[useMailGroups]
D --> E[MSW / API]
\`\`\`

## 3.2 ファイル構造

\`\`\`
src/features/mail-groups/
├── components/
│ └── mail-groups-filter-form.tsx # REQ-001, REQ-002
├── hooks/
│ └── use-mail-groups-filter.ts # REQ-001
└── schemas/
└── mail-groups-filter-schema.ts # REQ-001
\`\`\`

## 3.3 データフロー

...
```

---

### フェーズ 5 — Tasks

```bash
/vsdd-tasks mail-groups-filter
```

`planner` エージェントが設計をタスクに分解します。TDD（Red → Green → Refactor）順に並べられます。

**成果物:** `tasks.md`, `progress.md` 更新

```markdown
# Tasks: Mail Groups Filter

## TASK-001

**タイトル**: フィルタースキーマの作成
**対応要件**: REQ-001
**対応設計**: design.md §3.2
**種別**: Unit Test → Implementation
**ファイル**: `src/features/mail-groups/schemas/mail-groups-filter-schema.ts`

## TASK-002

**タイトル**: URL クエリ状態フックの実装
**対応要件**: REQ-001, REQ-002
**依存**: TASK-001
...
```

---

### フェーズ 6 — Review Plan

```bash
/vsdd-review-plan mail-groups-filter
```

`ecc:docs-lookup`（スタックドキュメント収集）→ `ecc:planner`（スコープ・依存リスク）→ `ecc:architect`（アーキテクチャ判定）の順で実行されます。

- REQ → 設計 → タスクのトレーサビリティ 6 項目チェック（いずれか ❌ で実装ブロック）
- タスク間の依存関係・抜け漏れ検出
- standard モードのみ: スタックドキュメントを参照した技術妥当性確認

**成果物:** `review-results/plan-review.md`（Traceability Coherence + Plan Review セクション）

---

### フェーズ 7 — Implement

```bash
# 全タスクを順番に実装
/vsdd-impl mail-groups-filter

# 特定タスクのみ（中断後の再開）
/vsdd-impl mail-groups-filter TASK-003
```

`tdd-workflow` スキルに従い、テストを先に書いてから実装します。

**各タスクのコミットメッセージ形式:**

```
feat(TASK-001): フィルタースキーマを追加

- MailGroupsFilterSchema を valibot で定義
- name, status フィールドのバリデーション追加
```

**成果物:** コード・テストファイル、`progress.md` 更新（各タスク完了時）

---

### フェーズ 8 — Code Review

```bash
/vsdd-review mail-groups-filter
```

native `code-review` / `/ecc:code-review` / `/ecc:security-review` の 3 段階で差分をレビューします。

**成果物:** `review-results/code-review.md`（CRITICAL / HIGH / MEDIUM / LOW の指摘事項 + Security Review セクション）

CRITICAL 指摘がある場合は、修正してから次フェーズに進みます。

---

### フェーズ 9 — PR

```bash
/vsdd-pr mail-groups-filter
```

`gh pr create` で GitHub PR を作成します。PR 本文には以下が含まれます。

- 実装の概要
- REQ → TASK → commit のトレーサビリティテーブル

```markdown
## Traceability

| 要件                             | タスク             | コミット         |
| -------------------------------- | ------------------ | ---------------- |
| REQ-001 名前フィルタリング       | TASK-001, TASK-002 | abc1234, def5678 |
| REQ-002 ステータスフィルタリング | TASK-003           | ghi9012          |
```

---

### Meta — Workflow 状態確認

```bash
# 現在作業中の slug の状態を確認
/vsdd-workflow

# 特定 slug の状態を確認
/vsdd-workflow mail-groups-filter
```

読み取り専用コマンドです。どのフェーズが完了・進行中・未着手かを表示します。

---

## 4. `--mode standard` と `--mode auto` の違い

モードは `/vsdd-init <slug> [--mode standard|auto]` で指定します（省略時は `standard`）。以降のスキルは `progress.md` の Mode を読み取ります。

### モードの選び方

| モード                       | 向いている人                           | 特徴                                                                                      |
| ---------------------------- | -------------------------------------- | ----------------------------------------------------------------------------------------- |
| **`standard`**（デフォルト） | エンジニア                             | 人間が意思決定。各フェーズと TDD サイクルで確認しながら進める。技術調査スキルを併用       |
| **`auto`**                   | 非エンジニア / AI に任せたいエンジニア | AI が草案・実装まで進める。承認は要件レビュー・プラン・コードレビューなど重要ゲートに集中 |

### 比較表

| 観点               | `standard`（デフォルト）                    | `auto`                                            |
| ------------------ | ------------------------------------------- | ------------------------------------------------- |
| **想定ユーザー**   | エンジニア                                  | 非エンジニア / AI に任せたいエンジニア            |
| **主導者**         | 人間が意思決定、AI がサポート               | AI が主導、人間は承認のみ                         |
| **要件定義**       | 人間が REQ を記述、AI が EARS 整形を支援    | AI が質問 → 回答から `requirements.md` を一括作成 |
| **要件レビュー**   | analyst + planner + docs-lookup + architect | analyst のみ（ビジネス観点を優先）                |
| **プラン review**  | docs-lookup + planner + architect           | architect のみ                                    |
| **実装**           | RED / GREEN / REFACTOR ごとに停止して確認   | TDD を連続実行、タスク完了まで自動ループ          |
| **コードレビュー** | 指摘一覧を提示、修正はエンジニアが判断      | CRITICAL / HIGH に修正案を併記（適用はしない）    |
| **承認ゲート**     | 全フェーズで `CONFIRM` が必要               | 重要なゲートのみ（フェーズ 3, 6, 8）              |
| **対話**           | AI に質問しながら進める                     | AI からの確認事項を最小化                         |

### フェーズごとのモード差（要約）

| フェーズ       | `standard`                     | `auto`                                                           |
| -------------- | ------------------------------ | ---------------------------------------------------------------- |
| 2 Requirements | テンプレートを人間が埋める     | 7 問のヒアリング後、AI が一括作成                                |
| 3 Review Req   | 技術実現性を含む多角的レビュー | 受入基準・ビジネス観点中心。懸念を平易に説明                     |
| 7 Implement    | TDD 各段階で一時停止           | タスク単位で自動コミット。`pnpm check` 失敗時は最大 3 回自己修正 |
| 8 Code Review  | エンジニア向けの技術指摘       | 重大な指摘に修正案を添える                                       |

### auto モードの使い方

```bash
/vsdd-init payment-refactor https://notion.so/... --mode auto
```

auto モードでは、AI は各フェーズを自動的に進め、承認ゲートに達したときだけ停止して確認を求めます。

```
AI: フェーズ 3（要件レビュー）が完了しました。
    以下の点が懸念されます：
    - REQ-003 の受入基準が具体的でない可能性があります

    続行するには CONFIRM vsdd-design と入力してください。
    修正が必要な場合は、修正内容を指示してください。
```

---

## 5. トレーサビリティ規約

VSDD の核心は「なぜこのコードがあるか」を追跡できるようにすることです。

### ID 書式

| 成果物   | 形式                       | 例                                          |
| -------- | -------------------------- | ------------------------------------------- |
| 要件     | `REQ-NNN`                  | `REQ-001`, `REQ-012`                        |
| タスク   | `TASK-NNN`                 | `TASK-001`, `TASK-015`                      |
| コミット | `feat/fix(TASK-NNN): 説明` | `feat(TASK-003): URLクエリ状態フックを追加` |

### トレーサビリティ連鎖

```
REQ-001（要件）
  ↓ 設計で参照
  design.md §3.2（設計）
  ↓ タスクで参照
  TASK-001（タスク）
  ↓ コミットで参照
  feat(TASK-001): フィルタースキーマを追加（コミット）
  ↓ PR で集約
  PR #123 — トレーサビリティテーブル（PR）
```

### ファイル内での参照例

`tasks.md` では必ず対応要件と設計セクションを明記します:

```markdown
## TASK-003

**対応要件**: REQ-001, REQ-002
**対応設計**: design.md §3.2
```

`review-results/code-review.md` では指摘事項に要件 ID を紐付けます:

```markdown
### [HIGH] REQ-001: 部分一致ロジックが大文字を考慮していない

ファイル: `src/features/mail-groups/hooks/use-mail-groups-filter.ts:45`
```

---

## 6. 承認ゲートの読み方と進め方

各フェーズの終わりに、AI は承認ゲートを提示します。

### 実際の出力例

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ フェーズ 2（Requirements）完了

成果物: .claude/specs/mail-groups-filter/requirements.md
要件数: 5 件（REQ-001 〜 REQ-005）

【確認が必要な点】
- REQ-004 の「適切なタイムアウト」は具体的な秒数を決める必要があります
- REQ-005 はスコープ外の可能性があります（チームで確認推奨）

次のフェーズ: vsdd-review-requirements（要件レビュー）

👉 続行: CONFIRM vsdd-review-requirements
   修正: 修正内容を日本語で指示してください
   スキップ: SKIP vsdd-review-requirements（非推奨）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 操作方法

| 操作               | 入力                                           | 効果                                   |
| ------------------ | ---------------------------------------------- | -------------------------------------- |
| 次フェーズへ進む   | `CONFIRM vsdd-review-requirements`              | フェーズ 3 を開始                      |
| 修正を指示         | `REQ-004 のタイムアウトは 30 秒にしてください` | 修正後に再度ゲートを表示               |
| スキップ（非推奨） | `SKIP vsdd-review-requirements`                 | レビューなしで次へ（品質低下のリスク） |

---

## 7. トラブルシュート / 再開方法

### 中断した場合

セッションが中断した場合、以下の手順で再開します。

```bash
# 1. 現在の状態を確認
/vsdd-workflow mail-groups-filter

# 出力例:
# フェーズ 1 Init         ✅ 完了
# フェーズ 2 Requirements ✅ 完了
# フェーズ 3 Review Req   ✅ 完了
# フェーズ 4 Design       ✅ 完了
# フェーズ 5 Tasks        ✅ 完了
# フェーズ 6 Review Plan  ✅ 完了
# フェーズ 7 Implement    🔄 進行中（TASK-003 まで完了）
# フェーズ 8 Code Review  ⬜ 未着手
# フェーズ 9 PR           ⬜ 未着手

# 2. 中断したタスクから再開
/vsdd-impl mail-groups-filter TASK-004
```

### よくある問題

| 問題                         | 対処                                                                                        |
| ---------------------------- | ------------------------------------------------------------------------------------------- |
| 要件が大きく変わった         | `/vsdd-requirements <slug>` を再実行して `requirements.md` を更新。フェーズ 3 以降をやり直す |
| タスクが多すぎる             | `/vsdd-tasks <slug>` を再実行して `tasks.md` を再生成。スコープを絞るよう AI に指示          |
| コミットメッセージが規約違反 | `git commit --amend` で修正。`feat(TASK-NNN):` 形式を維持する                               |
| `progress.md` の状態がズレた | `/vsdd-workflow <slug>` で確認後、AI に状態の修正を依頼                                      |
| テストが通らない             | `/vsdd-impl <slug> TASK-NNN` を再実行。AI に原因の調査を依頼                                 |

### スペックファイルの場所

```
.claude/specs/
└── <slug>/
    ├── source-notion.md    # 元の仕様ソース（Notion / 要件メモ）
    ├── requirements.md     # 要件（REQ-NNN）
    ├── design.md           # 設計
    ├── tasks.md            # タスク（TASK-NNN）
    ├── change-log.md       # フェーズ完了イベントログ
    ├── review-results/
    │   ├── requirement-review.md  # フェーズ 3 レビュー結果
    │   ├── plan-review.md         # フェーズ 6 レビュー結果
    │   └── code-review.md         # フェーズ 8 レビュー結果
    └── progress.md         # フェーズ・タスク進捗
```

---

## 8. 既存 ECC / Claude Code スキルとの対応関係

VSDD ワークフローは既存のスキル・エージェントを組み合わせて動作します。

| フェーズ                   | 使用されるスキル / エージェント | 役割                               |
| -------------------------- | ------------------------------- | ---------------------------------- |
| 3: Review Req              | `requirements-analyst` agent    | 要件の品質チェック（EARS・曖昧さ） |
| 3: Review Req              | `ecc:planner` agent             | スコープ・依存リスク確認           |
| 3: Review Req（standard）  | `ecc:docs-lookup` agent         | スタックドキュメント収集           |
| 3: Review Req（standard）  | `ecc:architect` agent           | 技術的実現可能性判定               |
| 4: Design                  | `/ecc:plan` command             | アーキテクチャ・ファイル構造設計   |
| 6: Review Plan（standard） | `ecc:docs-lookup` agent         | スタックドキュメント収集（先行）   |
| 6: Review Plan             | `ecc:planner` agent             | タスク分解・スコープ検証           |
| 6: Review Plan             | `ecc:architect` agent           | アーキテクチャ妥当性・技術リスク   |
| 7: Implement               | `/ecc:tdd-workflow` skill       | テスト駆動実装                     |
| 8: Code Review             | native `code-review` skill      | コード品質チェック                 |
| 8: Code Review             | `/ecc:code-review` command      | 7 カテゴリ体系的レビュー           |
| 8: Code Review             | `/ecc:security-review` skill    | セキュリティチェック               |
| 9: PR                      | `gh pr create`（CLI）           | GitHub PR の作成                   |

---

## 参考リンク

- [README](../README.md) — プラグイン概要・VSDD 思想・インストール
- [Usage Guide（使い方）](./vsdd-workflow-usage.md) — 初回セットアップから日次運用まで
- [Skills Detail（各 Skill の詳細）](./vsdd-workflow-skills.md) — Skill ごとの入出力・引数・呼出エージェント
- [VSDD 原典](https://gist.github.com/dollspace-gay/d8d3bc3ecf4188df049d7a4726bb2a00) / [VSDD Claude Code（Zenn）](https://zenn.dev/sc30gsw/articles/1373752d9713b3)
- [Harness design for long-running apps](https://www.anthropic.com/engineering/harness-design-long-running-apps)（Anthropic）
