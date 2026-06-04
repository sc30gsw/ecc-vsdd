# VSDD ワークフロー — Usage Guide

> **目的**: VSDD ワークフローを初めて使う人 / 日次運用する人向けの手順書。
> 概念・各 Skill の詳細は [vsdd-workflow.md](./vsdd-workflow.md) と [vsdd-workflow-skills.md](./vsdd-workflow-skills.md) を参照。

---

## 1. 初回セットアップ

リポジトリで初めて VSDD を使うときの手順。

> **前提: `/grill-with-docs` とは**
>
> 出典: [mattpocock/skills](https://github.com/mattpocock/skills) を基にした、ローカル配置のドメインヒアリング Skill (`/Users/<you>/...repo/.agents/skills/grill-with-docs/SKILL.md`)。
>
> - **役割**: 計画や用語をプロジェクト既存の語彙 (`context.md`) と過去の決定 (`docs/adr/`) に照らして「問い詰める」インタビュー型 Skill。曖昧表現は鋭く言い直しを迫る。
> - **動作**: 1 問ずつ質問 → ユーザ回答 → 結論を `context.md` / ADR にインラインで反映 → 次の枝へ。
> - **使い所**: `/vsdd-steering` が起こした `Q-XXX` の解消、`context.md` の `<!-- DRAFT -->` 確定、新規 spec 開始前のドメイン整合確認。
> - **ADR 化基準**: 「巻き戻しコスト高」「文脈なしでは驚き」「実際のトレードオフあり」3 つ揃った時のみ。
> - **付属テンプレ**: [CONTEXT-FORMAT.md](../../../../.agents/skills/grill-with-docs/CONTEXT-FORMAT.md) / [ADR-FORMAT.md](../../../../.agents/skills/grill-with-docs/ADR-FORMAT.md)

### 1-1. ステアリングを bootstrap

```bash
/vsdd-steering
```

`.claude/specs/_steering/` が作成され、以下 4 ファイルが生成されます。

| ファイル            | 内容                                    |
| ------------------- | --------------------------------------- |
| `tech.md`           | `package.json` から技術スタック一覧     |
| `structure.md`      | `src/features/` の feature インベントリ |
| `context.md`        | ドメイン用語集（DRAFT 付き）            |
| `open-questions.md` | 自動検出された未解決事項                |

### 1-2. Open Questions を確認 / 解決

```bash
cat .claude/specs/_steering/open-questions.md
```

`## Open` セクションの Q-XXX 項目を確認する。**解消自体に専用コマンドはなく**、以下 3 つの経路がある:

| 経路                    | 向いている場面                          | 工数                     |
| ----------------------- | --------------------------------------- | ------------------------ |
| **① 一括 grill (推奨)** | Q が複数あり、まとめて整理したい        | 中（1 セッションで全 Q） |
| **② 個別 grill**        | 1 件だけ深く議論したい                  | 小                       |
| **③ 完全手動編集**      | 自明な dismiss / 結論が既に決まっている | 極小                     |

#### ① 一括 grill (推奨)

複数の Q-XXX を 1 つの grill セッションでまとめて捌く。

```bash
/grill-with-docs .claude/specs/_steering/open-questions.md の Open 全件を順に解消したい
```

- **AI**: Q-001 から順に 1 問ずつ質問 → 結論を `context.md` に追記 / ADR 候補をフラグ
- **あなた (手動・セッション後)**: `open-questions.md` で解消済 Q を `## Resolved` / `## Dismissed` に移動

`/vsdd-steering` 直後に 7 件 Q がまとまって出るような状況に最適。

#### ② 個別 grill

1 件だけ深掘りしたい場合。詳細は [解消フロー (詳細)](#解消フロー-詳細) を参照。

#### ③ 完全手動編集 (grill なし)

grill を一切使わず、エディタで `open-questions.md` だけを書き換える。判断が明確 / dismiss だけで済む場合。

```bash
$EDITOR .claude/specs/_steering/open-questions.md
```

操作:

1. 対象 Q-XXX のブロックを `## Open` から切り取り
2. `## Resolved` または `## Dismissed` に貼り付け
3. `Status:` を `open` → `resolved` / `dismissed` に変更
4. `Resolved on:` / `Resolution:` (または `Dismissed on:` / `Reason:`) を追記
5. `context.md` 側は必要に応じて手動で entry を追記・修正

> 一括 grill の途中でも個別 grill でも、最終的に `## Open` を空にすれば `/vsdd-init` が通る。
> どの経路でも **`open-questions.md` の最終手動編集は不可避**（AI が勝手にセクション移動するとは限らない）。

#### 誰が何を更新するか

| 操作                                               | 実行者                  | 備考                                                               |
| -------------------------------------------------- | ----------------------- | ------------------------------------------------------------------ |
| grill 中の用語議論・`context.md` 更新              | AI (`/grill-with-docs`) | セッション中に該当 entry を都度追記・修正                          |
| `open-questions.md` の Status 変更・セクション移動 | **あなた（手動）**      | `## Open` から切り出し → `## Resolved` / `## Dismissed` へ貼り付け |
| `<!-- DRAFT -->` マーカ削除                        | **あなた（手動）**      | grill 中に消える場合もあるが、最終確認は手動推奨                   |
| ADR 作成                                           | **あなた（手動）**      | `docs/adr/NNNN-<slug>.md` を新規作成                               |

各項目の対応方針:

| 対応           | コマンド / 操作                                                                     |
| -------------- | ----------------------------------------------------------------------------------- |
| 用語を確定する | `/grill-with-docs` で grill → `context.md` 更新（AI）→ Q を Resolved に移動（手動） |
| ADR 化する     | `docs/adr/NNNN-<slug>.md` を手書きで作成 → Q を Resolved に移動（手動）             |
| 今期スコープ外 | Status を `dismissed` に変更 → `## Dismissed` へ移動（手動）                        |

> **ショートカット**: `/vsdd-init` が Q-XXX で停止したとき、チャットで `dismiss Q-005` と入力すると、AI が `open-questions.md` を更新して再開できる（grill 不要の却下向け）。

#### 解消フロー (詳細)

各 `Q-XXX` を「Open → Resolved or Dismissed」に動かす手順。

**ステップ:**

1. **対象 Q-XXX を 1 件選ぶ**
   `open-questions.md` の `## Open` から 1 件抜き出す（例: `Q-002: Group 概念が linked-groups と mail-groups で別物`）。

2. **判定**
   - **用語が確定できる** → 手順 3a (grill)
   - **横断アーキ決定が必要** → 手順 3b (ADR)
   - **今期スコープ外** → 手順 3c (dismiss)

3a. **grill で確定**

```bash
/grill-with-docs Q-002: LinkedGroup と MailGroup は完全に別概念か、共通の上位「Group」が必要か
```

- **grill 中 (AI)**: 矛盾・抜けを 1 問ずつ質問 → 回答 → 結論を `context.md` の該当 entry に追記
- **grill 後 (手動)**: DRAFT マーカ削除 + `open-questions.md` で Q-002 を `## Resolved` に移動

**具体例 — Before** (`open-questions.md` の `## Open`):

```markdown
### Q-002: `Group` 概念が linked-groups と mail-groups で別物

- Detected from: `src/features/linked-groups/types/`, `src/features/mail-groups/types/`
- Detected on: 2026-05-28
- Rule: 1 (term collision)
- Detail: `LinkedGroup` (Supplier/Consumer の紐付け) と `MailGroup` (通知メール束) はドメインが異なる…
- Status: open
```

**具体例 — grill 後の `context.md` 更新** (AI が追記するイメージ):

```diff
 ### LinkedGroup

-Supplier / Consumer の組合せを「グループ」単位で紐付けた管理単位。SupplierGroup と ConsumerGroup を内包する。
+Supplier / Consumer の紐付け条件を束ねる管理単位。**MailGroup（通知束）とは別概念**。共通の上位「Group」は設けない。
 <!-- DRAFT 2026-05-28 -->

 ### MailGroup

-通知メールの宛先・本文の束。`SpotCountRequest` で配信対象件数を見積もり、`NotificationMail` として発射される。
+通知メールの宛先・本文の束。**LinkedGroup とは別概念**。`SpotCountRequest` で配信対象件数を見積もり、`NotificationMail` として発射される。
 <!-- DRAFT 2026-05-28 -->
```

DRAFT 行は確定後に手動で削除:

```diff
 ### LinkedGroup
 Supplier / Consumer の紐付け条件を束ねる管理単位。**MailGroup（通知束）とは別概念**。
-<!-- DRAFT 2026-05-28 -->
```

**具体例 — After** (`open-questions.md` で手動移動):

```markdown
## Resolved

### Q-002: `Group` 概念が linked-groups と mail-groups で別物

- Detected from: `src/features/linked-groups/types/`, `src/features/mail-groups/types/`
- Detected on: 2026-05-28
- Rule: 1 (term collision)
- Detail: `LinkedGroup` (Supplier/Consumer の紐付け) と `MailGroup` (通知メール束) はドメインが異なる…
- Status: resolved
- Resolved on: 2026-05-28
- Resolution: 独立概念と確定。共通上位 Group は不要。`context.md` の LinkedGroup / MailGroup entry を更新。
```

`## Open` 側から Q-002 のブロックは **削除** する（コピーだけでは `/vsdd-init` のゲートは通らない）。

3b. **ADR で確定**

```bash
$EDITOR docs/adr/0002-group-terminology.md
```

[ADR-FORMAT.md](../../../../.agents/skills/grill-with-docs/ADR-FORMAT.md) テンプレを使用。後続の `/vsdd-design` で `Satisfies: ADR-0002` 引用される。Q を `## Resolved` に移動し `Resolution:` に ADR 番号を記載（手動）。

3c. **dismiss**

`open-questions.md` の該当 entry の `Status:` を `open` → `dismissed` に変更し、理由を追記。`## Open` から `## Dismissed` へ **手動で移動**:

```markdown
## Dismissed

### Q-005: `Filter` 型も feature ごとに別定義

- Detected from: 全 feature の `types/*Filter`
- Detected on: 2026-05-28
- Rule: 1 (term collision)
- Detail: `XxxFilter` 型が feature ごとに独立。共通化の必要性は低い…
- Status: dismissed
- Dismissed on: 2026-05-28
- Reason: 命名規約は明文化済み (CODING_GUIDELINES.md)、共通化メリット低い
```

4. **`## Open` が空であることを確認**

   残っている Q-XXX が 0 件になるまで 1〜3 を繰り返す。

5. **`/vsdd-init <slug>` 再実行**

   `## Open` が空なら後続フェーズに進める。

### 1-3. context.md の DRAFT を解消

`/vsdd-steering` が `context.md` に追加した glossary entry は `<!-- DRAFT YYYY-MM-DD -->` マーカ付き。ユーザ確認待ちの印。

**推奨: 一括 grill で全 DRAFT を確定**

DRAFT が多数 (例: bootstrap 直後の 10+ 件) ある場合は、まず一括 grill が最短。

```bash
/grill-with-docs .claude/specs/_steering/context.md の <!-- DRAFT --> 付き entry を順に確定したい
```

- **AI**: 各 entry を 1 件ずつ質問 → 回答を反映 → 関連 Q-XXX があれば連動して議論
- **あなた (セッション後・手動)**: 確定済 entry の `<!-- DRAFT YYYY-MM-DD -->` 行削除、関連 Q-XXX を `## Resolved` へ移動

[1-2 の一括 grill](#-一括-grill-推奨) と同じセッションで Q-XXX も同時に潰せると最も効率的。

---

**個別対応の判定:**

- 定義が **明確で正しい** → そのまま DRAFT マーカ削除 (手順 A)
- 定義に **疑問がある / 関連 Q-XXX と連動** → 個別 grill で確定 (手順 B)
- entry が **不要 / 重複** → 削除 or 統合 (手順 C)

**手順 A. 直接編集 (定義が明確)**

```bash
$EDITOR .claude/specs/_steering/context.md
```

該当 entry で:

1. 定義文を最終化（1〜3 行に整える）
2. 関連用語へ `[[other-term]]` リンクを追加
3. `<!-- DRAFT YYYY-MM-DD -->` 行を削除

例:

```diff
 ### Supplier
-小売電気事業者（卸電気の販売側）。Consumer と契約を通じて結びつく。
-<!-- DRAFT 2026-05-28 -->
+電力小売事業者。`[[Consumer]]` と契約で結ばれ、`[[LinkedGroup]]` 経由で複数 Consumer に紐付く。
```

**手順 B. grill で確定**

```bash
/grill-with-docs Supplier の定義を確定したい。卸電気事業者だけか、小売も含むか
```

- **grill 中 (AI)**: 質問 → 回答 → `context.md` の Supplier entry を更新
- **grill 後 (手動)**: DRAFT マーカ削除。関連 Q-XXX があれば `## Resolved` へ移動

**具体例 — grill 後の `context.md`**:

```diff
 ### Supplier

-小売電気事業者（卸電気の販売側）。Consumer と契約を通じて結びつく。
+電力小売事業者。`[[Consumer]]` と契約で結ばれ、`[[LinkedGroup]]` 経由で複数 Consumer に紐付く。
-<!-- DRAFT 2026-05-28 -->
```

Q-003（Supplier / Consumer の型重複）と連動している場合は、同じ grill セッションで議論し、解消後に `open-questions.md` へ追記:

```markdown
## Resolved

### Q-003: `Supplier` / `Consumer` が独立 feature と linked-groups 内型で重複

- Status: resolved
- Resolved on: 2026-05-28
- Resolution: `suppliers/types/Supplier` が正。linked-groups 内型は表示用 DTO。`context.md` Supplier / Consumer entry を更新。
```

`## Open` から Q-003 ブロックは削除する。

**手順 C. 削除 / 統合**

不要なら entry ごと削除。重複なら他 entry に統合してから削除側を消す。

**全件確定後の一括削除:**

```bash
# DRAFT が残らないことを確認
grep -c "<!-- DRAFT" .claude/specs/_steering/context.md

# 残量 0 でないなら個別に対応してから:
sed -i '' '/<!-- DRAFT [0-9-]\{10\} -->/d' .claude/specs/_steering/context.md
```

⚠ 未確定 entry がある状態で sed を走らせない。確定 entry のみ手動でマーカ削除する方が安全。

### 1-4. ADR を作成（任意）

横断的な決定（エラー設計、認証方針 等）は ADR として記録:

```
docs/adr/0001-<slug>.md
```

[grill-with-docs/ADR-FORMAT.md](../../../../.agents/skills/grill-with-docs/ADR-FORMAT.md) のテンプレートを使用。

---

## 2. 新しい spec を作る（日次運用）

新機能を実装する都度の手順。

### 2-1. spec ディレクトリを初期化

```bash
# Notion URL あり
/vsdd-init mail-groups-filter https://www.notion.so/<workspace>/xxxx

# Notion URL なし
/vsdd-init mail-groups-filter

# AI 主導モード
/vsdd-init payment-refactor https://notion.so/... --mode auto
```

**内部処理**:

1. **Step 0**: `/vsdd-steering` を内部呼出 → 新規 Q-XXX があれば停止
2. **Step 1**: slug を kebab-case で検証
3. **Step 2**: `.claude/specs/<slug>/` を作成
4. **Step 3**: Notion URL があれば `source-notion.md` に保存
5. **Step 4**: `progress.md` / `change-log.md` を初期化

### 2-2. 中断された場合

`/vsdd-init` が新規 Q-XXX で停止した時:

```bash
# 1. open-questions.md を確認
cat .claude/specs/_steering/open-questions.md

# 2-a. grill で解決
/grill-with-docs <Q-id について議論したい内容>

# 2-b. または dismiss
# open-questions.md の該当エントリに dismissed フラグを手書きで追記

# 3. /vsdd-init を再実行
/vsdd-init <slug>
```

---

## 3. spec を進める

`/vsdd-init` 完了後、Phase 2 以降を順に実行。各 Phase 完了時に承認ゲート (`CONFIRM`) が出る。

```bash
/vsdd-requirements <slug>          # Phase 2
# → CONFIRM vsdd-review-requirements
/vsdd-review-requirements <slug>   # Phase 3
# → CONFIRM vsdd-design
/vsdd-design <slug>                # Phase 4
# → CONFIRM vsdd-tasks
/vsdd-tasks <slug>                 # Phase 5
# → CONFIRM vsdd-review-plan
/vsdd-review-plan <slug>           # Phase 6
# → CONFIRM vsdd-impl
/vsdd-impl <slug>                  # Phase 7
# → CONFIRM vsdd-review
/vsdd-review <slug>                # Phase 8
# → CONFIRM vsdd-pr
/vsdd-pr <slug>                    # Phase 9
```

### 3-1. 中断と再開

セッション中断後の再開:

```bash
# 状態確認
/vsdd-workflow <slug>

# 表示例:
# Phase 0 Steering     ✅ 完了
# Phase 1 Init         ✅ 完了
# Phase 2 Requirements ✅ 完了
# Phase 3 Review Req   ✅ 完了
# Phase 4 Design       ✅ 完了
# Phase 5 Tasks        ✅ 完了
# Phase 6 Review Plan  ✅ 完了
# Phase 7 Implement    🔄 進行中（TASK-003 まで完了）
# Phase 8 Code Review  ⬜ 未着手
# Phase 9 PR           ⬜ 未着手

# 中断箇所から再開
/vsdd-impl <slug> TASK-004
```

---

## 4. ステアリングをメンテナンスする

`/vsdd-steering` は冪等な refresh です。コードベースが変わったタイミングで再実行。

### 4-1. 通常 refresh

```bash
/vsdd-steering
```

自動セクション（`tech.md` / `structure.md`）は再生成、手動セクション（`context.md` Manual Notes 等）は保持。

### 4-2. ドライラン

```bash
/vsdd-steering --dry-run
```

差分プレビューのみ出力。書込みなし。

### 4-3. 強制再 bootstrap

```bash
/vsdd-steering --force
```

既存 `_steering/` を `_steering/.bak/` に退避し、4 ファイル全てを初期化。手動セクションも消える点に注意。

### 4-4. 推奨タイミング

- 新しい feature を追加 / 削除した直後
- `package.json` の major dep を変更した直後
- 既存 feature の `types/` `schemas/` `api/` を大幅に変更した直後
- `/vsdd-init` 実行前（自動呼出されるので手動実行は任意）

---

## 5. よくある問題

| 問題                                              | 対処                                                                                                                    |
| ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `/vsdd-init` が新規 Q-XXX で停止する               | `cat .claude/specs/_steering/open-questions.md` で確認し、grill or dismiss してから再実行                               |
| `_steering/` が見つからないと言われる             | `/vsdd-steering` を実行                                                                                                  |
| `context.md` の DRAFT マーカーを消したい          | grill-with-docs で議論 → 確定したら手動で `<!-- DRAFT -->` を削除                                                       |
| `structure.md` が古い                             | `/vsdd-steering` で refresh                                                                                              |
| ADR を作りたい                                    | `docs/adr/NNNN-<slug>.md` を手書きで作成 ([ADR フォーマット](../../../../.agents/skills/grill-with-docs/ADR-FORMAT.md)) |
| 既存 spec の `requirements.md` が steering と矛盾 | `/vsdd-review-requirements <slug>` で Check 8 (Term Drift) が検出。grill で context.md を更新                            |

---

## 6. ファイル配置のサマリ

```
.claude/specs/
├── _steering/                        # ← /vsdd-steering が管理
│   ├── tech.md
│   ├── structure.md
│   ├── context.md
│   └── open-questions.md
└── <slug>/                           # ← /vsdd-init が作成
    ├── source-notion.md
    ├── requirements.md
    ├── design.md
    ├── tasks.md
    ├── progress.md
    ├── change-log.md
    └── review-results/
        ├── requirement-review.md
        ├── plan-review.md
        └── code-review.md

docs/adr/                             # ← 手書き（横断決定）
└── NNNN-<slug>.md
```

---

## 参考リンク

- [VSDD ワークフロー（概念ガイド）](./vsdd-workflow.md)
- [Skills Detail（各 Skill の詳細）](./vsdd-workflow-skills.md)
- [VSDD ワークフロー インタラクティブ図](./vsdd-workflow.html)
