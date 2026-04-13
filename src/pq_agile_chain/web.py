from __future__ import annotations

import os
import secrets
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .chain import ChainValidationError
from .crypto_backends import BackendError
from .service import ChainWorkspace, WorkspaceError

INDEX_HTML = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>jrti.org/qc | PQ-Agile Chain</title>
  <style>
    :root {
      color-scheme: light dark;
      --bg: #f6f3ee;
      --panel: #fffdfa;
      --text: #181512;
      --muted: #5b534c;
      --line: #d8d0c7;
      --accent: #35261c;
      --accent-soft: #efe7dd;
    }
    @media (prefers-color-scheme: dark) {
      :root {
        --bg: #161311;
        --panel: #1f1a16;
        --text: #f2ede8;
        --muted: #c1b6aa;
        --line: #3c342d;
        --accent: #f2ede8;
        --accent-soft: #2c241f;
      }
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 16px/1.55 "Noto Serif KR", "Iowan Old Style", "Apple SD Gothic Neo", serif;
    }
    main {
      max-width: 1080px;
      margin: 0 auto;
      padding: 40px 20px 64px;
    }
    header {
      margin-bottom: 28px;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--line);
    }
    h1, h2, h3 { margin: 0 0 12px; font-weight: 700; }
    h1 { font-size: 2rem; letter-spacing: -0.02em; }
    h2 { font-size: 1.1rem; margin-top: 0; }
    p { margin: 0 0 12px; }
    .muted { color: var(--muted); }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px;
      margin-bottom: 16px;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 18px;
      box-shadow: 0 1px 0 rgba(0,0,0,0.03);
    }
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin: 18px 0 0;
    }
    .header-tools {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: 12px;
      align-items: end;
    }
    @media (min-width: 760px) {
      .header-tools {
        grid-template-columns: auto minmax(260px, 360px);
      }
    }
    .toolbar-block {
      min-width: 0;
    }
    .toolbar-block .toolbar {
      margin-top: 0;
    }
    .token-label {
      margin-bottom: 0;
    }
    .token-help {
      margin-top: 6px;
      font-size: 0.9rem;
    }
    button {
      border: 1px solid var(--accent);
      background: var(--accent);
      color: var(--bg);
      border-radius: 999px;
      padding: 10px 14px;
      cursor: pointer;
      font: inherit;
    }
    button.secondary {
      background: transparent;
      color: var(--accent);
    }
    button:disabled {
      opacity: 0.55;
      cursor: default;
    }
    label {
      display: block;
      margin-bottom: 12px;
      font-size: 0.95rem;
    }
    input, select {
      width: 100%;
      margin-top: 6px;
      padding: 9px 11px;
      border-radius: 10px;
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--text);
      font: inherit;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.95rem;
    }
    th, td {
      text-align: left;
      padding: 10px 8px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
    }
    th { color: var(--muted); font-weight: 600; }
    code, pre {
      font-family: "SFMono-Regular", "SF Mono", Menlo, Consolas, monospace;
      font-size: 0.88rem;
    }
    pre {
      margin: 0;
      padding: 12px;
      border-radius: 10px;
      background: var(--accent-soft);
      overflow: auto;
    }
    .status {
      min-height: 24px;
      margin: 12px 0 0;
      color: var(--muted);
    }
    .pill {
      display: inline-block;
      padding: 2px 8px;
      border: 1px solid var(--line);
      border-radius: 999px;
      font-size: 0.82rem;
      margin-left: 8px;
    }
  </style>
</head>
<body>
  <main>
    <header>
      <p class="muted">JRTI · 법률·언어·인공지능 통섭연구소</p>
      <h1>jrti.org/qc</h1>
      <p>PQ-Agile Chain demonstrator. Post-quantum signatures are provided by <code>pqcrypto</code>; the chain logic focuses on account-level key rotation and security floors.</p>
      <div class="header-tools">
        <div class="toolbar-block">
          <div class="toolbar">
            <button id="reset-demo">데모 초기화</button>
            <button id="mine-button">보류 트랜잭션 채굴</button>
            <button id="refresh-button" class="secondary">상태 새로고침</button>
          </div>
        </div>
        <div class="toolbar-block">
          <label class="token-label">관리 토큰
            <input id="admin-token" type="password" autocomplete="off" placeholder="Optional X-Admin-Token">
          </label>
          <p class="muted token-help">쓰기 API가 보호된 배포에서는 이 값을 브라우저 세션에 저장해 함께 전송합니다.</p>
        </div>
      </div>
      <div id="status" class="status"></div>
    </header>

    <section class="grid">
      <article class="panel">
        <h2>체인 요약</h2>
        <div id="chain-summary" class="muted">데이터를 불러오는 중입니다.</div>
      </article>
      <article class="panel">
        <h2>워크스페이스</h2>
        <div id="workspace-summary" class="muted">데이터를 불러오는 중입니다.</div>
      </article>
    </section>

    <section class="grid">
      <article class="panel">
        <h2>송금</h2>
        <label>보내는 지갑
          <select id="transfer-sender"></select>
        </label>
        <label>받는 지갑
          <select id="transfer-recipient"></select>
        </label>
        <label>금액
          <input id="transfer-amount" type="number" min="1" value="10">
        </label>
        <button id="transfer-button">송금 추가</button>
      </article>
      <article class="panel">
        <h2>키 회전</h2>
        <label>현재 지갑
          <select id="rotate-wallet"></select>
        </label>
        <label>새 알고리즘
          <select id="rotate-algo"></select>
        </label>
        <label>새 security floor
          <input id="rotate-floor" type="number" min="1" value="5">
        </label>
        <button id="rotate-button">회전 트랜잭션 추가</button>
      </article>
    </section>

    <section class="grid">
      <article class="panel">
        <h2>계정 상태</h2>
        <div id="accounts-table"></div>
      </article>
      <article class="panel">
        <h2>지갑</h2>
        <div id="wallets-table"></div>
      </article>
    </section>

    <section class="grid">
      <article class="panel">
        <h2>최근 블록</h2>
        <div class="toolbar">
          <button id="blocks-prev" class="secondary">이전 페이지</button>
          <button id="blocks-next" class="secondary">다음 페이지</button>
          <span id="blocks-page-status" class="muted"></span>
        </div>
        <div id="blocks-table"></div>
      </article>
      <article class="panel">
        <h2>보류 트랜잭션</h2>
        <div id="mempool-view"></div>
      </article>
    </section>
  </main>

  <script>
    const state = { snapshot: null, blockOffset: 0, blockLimit: 10, blockTotal: 0 };
    const statusEl = document.getElementById("status");
    const basePath = window.location.pathname.startsWith("/qc") ? "/qc" : "";
    const blockPrevButton = document.getElementById("blocks-prev");
    const blockNextButton = document.getElementById("blocks-next");
    const adminTokenInput = document.getElementById("admin-token");
    const tokenStorageKey = "pqAgileChainAdminToken";

    try {
      adminTokenInput.value = window.sessionStorage.getItem(tokenStorageKey) || "";
    } catch (_error) {
      adminTokenInput.value = "";
    }

    adminTokenInput.addEventListener("input", () => {
      try {
        if (adminTokenInput.value) {
          window.sessionStorage.setItem(tokenStorageKey, adminTokenInput.value);
        } else {
          window.sessionStorage.removeItem(tokenStorageKey);
        }
      } catch (_error) {
        // Ignore storage failures and continue with the in-memory field value.
      }
    });

    function setStatus(message, isError = false) {
      statusEl.textContent = message;
      statusEl.style.color = isError ? "#b42318" : "";
    }

    function optionHtml(value, label) {
      return `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`;
    }

    function escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    }

    function renderTable(columns, rows) {
      if (!rows.length) {
        return '<p class="muted">표시할 항목이 없습니다.</p>';
      }
      const head = columns.map((column) => `<th>${column.label}</th>`).join("");
      const body = rows.map((row) => {
        const cells = columns.map((column) => {
          const value = row[column.key] ?? "";
          return `<td>${column.raw ? value : escapeHtml(value)}</td>`;
        }).join("");
        return `<tr>${cells}</tr>`;
      }).join("");
      return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
    }

    function renderSnapshot(snapshot) {
      state.snapshot = snapshot;

      const chain = snapshot.chain;
      const wallets = snapshot.wallets || [];
      const accounts = snapshot.accounts || [];
      const mempool = snapshot.mempool || [];
      const latestBlock = snapshot.latest_block;

      document.getElementById("chain-summary").innerHTML = chain
        ? `<p>블록 수: <strong>${chain.block_count}</strong></p>
           <p>난이도: <strong>${chain.difficulty}</strong></p>
           <p>보류 트랜잭션: <strong>${chain.mempool_count}</strong></p>
           <p>마지막 블록 해시: <code>${latestBlock ? `${latestBlock.block_hash.slice(0, 24)}...` : "없음"}</code></p>`
        : '<p class="muted">아직 체인이 없습니다. "데모 초기화"를 먼저 실행하세요.</p>';

      document.getElementById("workspace-summary").innerHTML =
        `<p>데이터 디렉터리: <code>${snapshot.workspace.root_dir}</code></p>
         <p>체인 파일: <code>${snapshot.workspace.chain_path}</code></p>
         <p>지원 알고리즘: ${snapshot.supported_algorithms.map((item) => `<code>${item}</code>`).join(", ")}</p>`;

      document.getElementById("accounts-table").innerHTML = renderTable(
        [
          { key: "label", label: "label" },
          { key: "account_id", label: "account_id" },
          { key: "algo_id", label: "algo" },
          { key: "security_floor", label: "floor" },
          { key: "nonce", label: "nonce" },
          { key: "balance", label: "balance" }
        ],
        accounts
      );

      document.getElementById("wallets-table").innerHTML = renderTable(
        [
          { key: "wallet_id", label: "wallet_id" },
          { key: "label", label: "label" },
          { key: "algo_id", label: "algo" },
          { key: "security_floor", label: "floor" },
          { key: "secret_storage", label: "secret storage" },
          { key: "active_on_chain", label: "active" }
        ],
        wallets.map((wallet) => ({
          ...wallet,
          active_on_chain: wallet.active_on_chain ? "yes" : "no"
        }))
      );

      document.getElementById("mempool-view").innerHTML = mempool.length
        ? `<pre>${JSON.stringify(mempool, null, 2)}</pre>`
        : '<p class="muted">보류 중인 트랜잭션이 없습니다.</p>';

      const walletOptions = wallets.map((wallet) =>
        optionHtml(
          wallet.wallet_id,
          `${wallet.wallet_id} · ${wallet.algo_id}${wallet.active_on_chain ? " (active)" : ""}`
        )
      ).join("");
      document.getElementById("transfer-sender").innerHTML = walletOptions;
      document.getElementById("transfer-recipient").innerHTML = walletOptions;
      document.getElementById("rotate-wallet").innerHTML = walletOptions;
      document.getElementById("rotate-algo").innerHTML = snapshot.supported_algorithms
        .map((algo) => optionHtml(algo, algo))
        .join("");

      const activeWallet = wallets.find((wallet) => wallet.active_on_chain);
      if (activeWallet) {
        document.getElementById("transfer-sender").value = activeWallet.wallet_id;
        document.getElementById("rotate-wallet").value = activeWallet.wallet_id;
        document.getElementById("rotate-floor").value = String(activeWallet.security_floor);
      }

      const recipientWallet = wallets.find((wallet) => wallet.wallet_id !== activeWallet?.wallet_id);
      if (recipientWallet) {
        document.getElementById("transfer-recipient").value = recipientWallet.wallet_id;
      }
    }

    function renderBlocksPage(page) {
      state.blockOffset = page.offset;
      state.blockTotal = page.total;
      const pageStart = page.total ? page.offset + 1 : 0;
      const pageEnd = Math.min(page.offset + page.items.length, page.total);

      document.getElementById("blocks-table").innerHTML = renderTable(
        [
          { key: "index", label: "height" },
          { key: "created_at", label: "timestamp" },
          { key: "tx_count", label: "tx" },
          { key: "short_hash", label: "hash", raw: true }
        ],
        page.items.map((block) => ({
          ...block,
          short_hash: `<code>${block.block_hash.slice(0, 20)}...</code>`
        }))
      );

      document.getElementById("blocks-page-status").textContent =
        page.total
          ? `${pageStart}-${pageEnd} / ${page.total}`
          : "0 / 0";
      blockPrevButton.disabled = page.offset === 0;
      blockNextButton.disabled = page.offset + page.limit >= page.total;
    }

    function apiUrl(path) {
      return `${basePath}${path}`;
    }

    function writeHeaders() {
      const headers = { "Content-Type": "application/json" };
      if (adminTokenInput.value) {
        headers["X-Admin-Token"] = adminTokenInput.value;
      }
      return headers;
    }

    async function getJson(path) {
      const response = await fetch(apiUrl(path));
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "request failed");
      }
      return data;
    }

    async function callApi(path, payload) {
      const response = await fetch(apiUrl(path), {
        method: "POST",
        headers: writeHeaders(),
        body: JSON.stringify(payload || {})
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "request failed");
      }
      return data;
    }

    async function loadBlocks(offset = state.blockOffset) {
      const page = await getJson(`/api/blocks?offset=${offset}&limit=${state.blockLimit}`);
      renderBlocksPage(page);
    }

    async function refreshState(resetBlockOffset = false) {
      const nextOffset = resetBlockOffset ? 0 : state.blockOffset;
      const [snapshot, blockPage] = await Promise.all([
        getJson("/api/state"),
        getJson(`/api/blocks?offset=${nextOffset}&limit=${state.blockLimit}`)
      ]);
      renderSnapshot(snapshot);
      renderBlocksPage(blockPage);
    }

    document.getElementById("refresh-button").addEventListener("click", async () => {
      setStatus("상태를 새로 불러오는 중입니다.");
      try {
        await refreshState();
        setStatus("최신 상태를 불러왔습니다.");
      } catch (error) {
        setStatus(error.message, true);
      }
    });

    document.getElementById("reset-demo").addEventListener("click", async () => {
      setStatus("데모 체인을 다시 생성하는 중입니다.");
      try {
        const data = await callApi("/api/demo/bootstrap", { difficulty: 2 });
        renderSnapshot(data.snapshot);
        await loadBlocks(0);
        setStatus("데모 체인을 초기화했습니다.");
      } catch (error) {
        setStatus(error.message, true);
      }
    });

    document.getElementById("transfer-button").addEventListener("click", async () => {
      setStatus("송금 트랜잭션을 추가하는 중입니다.");
      try {
        const data = await callApi("/api/transfer", {
          sender_wallet_id: document.getElementById("transfer-sender").value,
          recipient_wallet_id: document.getElementById("transfer-recipient").value,
          amount: Number(document.getElementById("transfer-amount").value)
        });
        renderSnapshot(data.snapshot);
        await loadBlocks(0);
        setStatus("송금 트랜잭션을 mempool에 추가했습니다.");
      } catch (error) {
        setStatus(error.message, true);
      }
    });

    document.getElementById("rotate-button").addEventListener("click", async () => {
      setStatus("키 회전 트랜잭션을 추가하는 중입니다.");
      try {
        const currentWalletId = document.getElementById("rotate-wallet").value;
        const algo = document.getElementById("rotate-algo").value;
        const nextId = `${currentWalletId}-${algo.replace(/[^a-z0-9_-]+/g, "-")}`;
        const data = await callApi("/api/rotate", {
          current_wallet_id: currentWalletId,
          new_algo_id: algo,
          new_wallet_id: nextId.toLowerCase(),
          new_security_floor: Number(document.getElementById("rotate-floor").value)
        });
        renderSnapshot(data.snapshot);
        await loadBlocks(0);
        setStatus(`회전 트랜잭션을 추가했습니다. 새 지갑: ${data.wallet_id}`);
      } catch (error) {
        setStatus(error.message, true);
      }
    });

    document.getElementById("mine-button").addEventListener("click", async () => {
      setStatus("보류 트랜잭션을 채굴하는 중입니다.");
      try {
        const data = await callApi("/api/mine");
        renderSnapshot(data.snapshot);
        await loadBlocks(0);
        setStatus(`블록 #${data.block.index}을 채굴했습니다.`);
      } catch (error) {
        setStatus(error.message, true);
      }
    });

    blockPrevButton.addEventListener("click", async () => {
      try {
        await loadBlocks(Math.max(0, state.blockOffset - state.blockLimit));
      } catch (error) {
        setStatus(error.message, true);
      }
    });

    blockNextButton.addEventListener("click", async () => {
      try {
        await loadBlocks(state.blockOffset + state.blockLimit);
      } catch (error) {
        setStatus(error.message, true);
      }
    });

    refreshState().then(
      () => setStatus("상태를 불러왔습니다."),
      (error) => setStatus(error.message, true)
    );
  </script>
</body>
</html>
"""


class DemoBootstrapRequest(BaseModel):
    difficulty: int = Field(default=2, ge=1, le=5)


class TransferRequest(BaseModel):
    sender_wallet_id: str
    recipient_wallet_id: str | None = None
    recipient_account_id: str | None = None
    amount: int = Field(ge=1)


class RotateRequest(BaseModel):
    current_wallet_id: str
    new_algo_id: str
    new_wallet_id: str | None = None
    new_label: str | None = None
    new_security_floor: int | None = Field(default=None, ge=1)


def create_app(root_dir: str | Path | None = None) -> FastAPI:
    workspace = ChainWorkspace(root_dir)
    admin_token = os.environ.get("PQ_AGILE_CHAIN_ADMIN_TOKEN")
    if admin_token == "":
        raise ValueError("PQ_AGILE_CHAIN_ADMIN_TOKEN must not be empty")
    app = FastAPI(
        title="PQ-Agile Chain",
        version="0.3.0",
        summary="Account-based post-quantum chain explorer with encrypted wallets, paginated history, replay validation, and on-chain key rotation.",
    )

    def require_write_access(
        x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
        authorization: str | None = Header(default=None),
    ) -> None:
        if not admin_token:
            return

        bearer_token = None
        if authorization:
            scheme, _, value = authorization.partition(" ")
            if scheme.lower() == "bearer" and value:
                bearer_token = value

        provided_token = x_admin_token or bearer_token
        if not provided_token or not secrets.compare_digest(provided_token, admin_token):
            raise HTTPException(
                status_code=403,
                detail="Write operations require a valid admin token",
            )

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return INDEX_HTML

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/state")
    def state() -> dict:
        return workspace.snapshot()

    @app.get("/api/blocks")
    def blocks(
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=10, ge=1, le=100),
    ) -> dict:
        return workspace.list_blocks(offset=offset, limit=limit)

    @app.get("/api/transactions")
    def transactions(
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=50, ge=1, le=200),
        include_mempool: bool = Query(default=True),
    ) -> dict:
        return workspace.list_transactions(
            offset=offset,
            limit=limit,
            include_mempool=include_mempool,
        )

    @app.post("/api/demo/bootstrap")
    def bootstrap_demo(
        payload: DemoBootstrapRequest,
        _: None = Depends(require_write_access),
    ) -> dict:
        return {"snapshot": workspace.reset_demo(difficulty=payload.difficulty)}

    @app.post("/api/transfer")
    def transfer(
        payload: TransferRequest,
        _: None = Depends(require_write_access),
    ) -> dict:
        return workspace.transfer(
            sender_wallet_id=payload.sender_wallet_id,
            recipient_wallet_id=payload.recipient_wallet_id,
            recipient_account_id=payload.recipient_account_id,
            amount=payload.amount,
        )

    @app.post("/api/rotate")
    def rotate(
        payload: RotateRequest,
        _: None = Depends(require_write_access),
    ) -> dict:
        return workspace.rotate(
            current_wallet_id=payload.current_wallet_id,
            new_algo_id=payload.new_algo_id,
            new_wallet_id=payload.new_wallet_id,
            new_label=payload.new_label,
            new_security_floor=payload.new_security_floor,
        )

    @app.post("/api/mine")
    def mine(_: None = Depends(require_write_access)) -> dict:
        return workspace.mine()

    @app.exception_handler(WorkspaceError)
    @app.exception_handler(ChainValidationError)
    @app.exception_handler(BackendError)
    async def handle_workspace_error(_, exc: Exception):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=400, content={"detail": str(exc)})

    return app


app = create_app()


def run() -> None:
    uvicorn.run("pq_agile_chain.web:app", host="127.0.0.1", port=8401, reload=False)
