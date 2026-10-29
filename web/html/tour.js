/* 逐步導覽：高亮頁面元素 + 說明卡，無外部套件。
   window.startTour(name) 啟動；window.maybeAutoTour(name) 第一次進入該頁時提示一次 (localStorage 記錄)。
   name 對應下面 TOURS 的 key；專案頁依分頁分成 project-parts / project-drawings / … */
(function () {
  const TOURS = {
    projects: [
      { sel: '#newp', title: '1. 建立專案', text: '一個專案 = 一張料單 = 一個案場。填案場、板厚（下拉常用板厚，按 ＋ 可新增）、日期後按「建立空白專案」。訂單編號系統自動編。' },
      { sel: '#imp', title: '2. 或從 Excel 匯入', text: '已經有舊格式的 Excel 料單？直接選檔案匯入，手動填的封邊、備註都會保留。' },
      { sel: '#plist', title: '3. 專案列表', text: '點訂單編號或案場進入專案。右邊的 ⬇ Excel 可直接匯出料單；搜尋框可用案場或編號過濾。' },
      { sel: '.topbar nav', title: '4. 其他頁面', text: '「客戶」建設計師/業務資料；「基礎資料」查色號單價、零件目錄、標記；「回饋」看操作者回報；「更新通知」看哪些回饋已修好、每版改了什麼（有新版本時會亮紅點）。每一頁右上角都有「？ 導覽」。' },
      { sel: '#fbbtn', title: '5. 意見回饋', text: '任何時候覺得怪、算錯、想要新功能，按這裡寫下來送出，會自動記錄你在哪一頁。可以附截圖：Win+Shift+S 截完在視窗裡 Ctrl+V 貼上，或拖檔案進去，問題才好對症處理。' },
    ],
    'project-parts': [
      { sel: '#quickstart', title: '快速開始', text: '這張卡片會告訴你這個專案做到哪：圖面、櫃體、對圖、尺寸、色號、草稿列、匯出。做完一項會自動打勾，點圓點跳到該分頁。' },
      { sel: '.tabs', title: '分頁', text: '料單＝打板材；圖面＝設計師 PDF；統計/叫料＝自我檢查；計價清單＝報價；標籤列印/流水號＝工廠用。每個分頁都有自己的導覽。' },
      { sel: '#togglehdr', title: '表頭', text: '要改案場、交貨日、板厚、狀態、修改日期，按這裡展開。' },
      { sel: '#exportbtn', title: '匯出 Excel 料單', text: '隨時可按，產出原 6.0 版格式的 Excel（含標籤列印版等分頁）。' },
      { sel: '#newcab', title: '新增櫃體', text: '填名稱與高/深/寬，選類型（標準櫃 / 水槽櫃 / 油機吊櫃…，可在基礎資料→櫃體範本自訂），勾不勾「有門片」「內部隔板」決定要不要產生門板與中立板/活隔/固隔。櫃身與門片可以填不同色號。' },
      { sel: '#showcat', title: '類別欄', text: '料單表格的「類別」欄平常用不到，預設隱藏；要看或要改時勾這裡。類別仍會依名稱自動判斷。' },
      { sel: '.cab-head', title: '櫃體列', text: '「複製櫃體」做同款不同寬最快；「套用色號」把櫃身色套到板材、門片色套到門片/面板；「圖面頁 / 圖上編號 / 看圖」對照設計圖。' },
      { sel: '.cab:not(.collapsed) .tablewrap', title: '板材表格', text: '名稱直接打字有建議；藍底是自動算的（封邊、備註、提醒、才數、金額），可以直接改，改過變黃底，↺ 恢復。按 Enter 或點別處就存。' },
      { sel: '[data-addpart]', title: '加板材', text: '「＋板材」加一列空白；「＋桶身 / ＋外部 / ＋其它五金」直接加指定類別。名稱沒填的列是紅框草稿，不會進報表。備註4 可從下拉清單選（把手、特殊…，清單在基礎資料→下拉清單→備註4）。' },
      { sel: '.nav', title: '櫃體導覽', text: '櫃體多的時候從這裡跳；「收合」只留標題列好捲動。' },
    ],
    'project-drawings': [
      { sel: '#up', title: '上傳圖面', text: '設計師的 PDF 整份上傳（一頁一區域），也可傳 JPG/PNG 照片。備註寫版本，例如「設計師 10/16 版」。' },
      { sel: '.thumbs', title: '每頁縮圖', text: '點縮圖開大圖，可翻頁、開原尺寸、下載原檔。縮圖下方會列出已對應到這一頁的櫃號。' },
      { sel: '.tabs', title: '回料單對圖', text: '回「料單」分頁，在每個櫃體列選「圖面頁」並填圖上編號 ①②③，之後按「看圖」即可對照。' },
    ],
    'project-summary': [
      { sel: '.kpi', title: '總數', text: '板材總片數、總才數、未稅金額、櫃體數。金額是 0 通常是色號沒填或該板厚沒有單價。' },
      { sel: '#tabbody table', title: '每櫃明細', text: '每個櫃體的片數、才數、金額。與 Excel 料單表頭的「板材總片數 / 總才數」對應。' },
    ],
    'project-quote': [
      { sel: '#qs', title: '計價設定', text: '板材折數留空＝用客戶設定；安裝可手填或勾「自動」（折後板材 × 客戶安裝折數）；運費手填。改完按「儲存並重算」。' },
      { sel: '#qm', title: '報價單資料', text: '設計公司、聯絡人、施工類別、進場日期等會印在報價單上。' },
      { sel: '#feesuggest', title: '加工費', text: '從「基礎資料 → 加工/封邊」的牌價選項目，或按「依料單備註帶入」自動抓 斜把 / 打型 / Z把 / 崁把手，再核對數量。' },
      { sel: '.kpi', title: '合計', text: '板材牌價 → 折數 → 折後板材 + 加工費 + 安裝 + 運費 → 5% 稅 → 總金額。右上「列印報價單」用公司資料的抬頭與匯款資訊。' },
    ],
    'project-partslist': [
      { sel: '#printpl', title: '零件單', text: '料單裡五金類板件依名稱彙總，規格/型號從五金配件目錄比對帶入。按「列印零件單」交給倉庫備料。' },
    ],
    'project-labels': [
      { sel: '#xlsx', title: '下載 Excel / CSV', text: '每片板材一列（不含五金），欄位與原「標籤列印版」相同。Excel 可直接開、改、印；CSV 給標籤機匯入。' },
      { sel: '#tabbody .tablewrap', title: '標籤內容', text: '訂單、案場、櫃號、編號、尺寸、封邊、色號、封邊色號、備註、狀態、批次、交貨日。' },
    ],
    'project-serials': [
      { sel: '#scan', title: '掃描', text: '輸入流水號（掃描槍或手 key），按 Enter 或「開板掃描」；包裝完按「包裝掃描」。掃錯按該格的 v ✕ 取消。' },
      { sel: '#tabbody .tablewrap', title: '流水號表', text: '每片板材一個固定的流水號與標籤碼（編號 + 4 碼）。之後增刪板材不會讓已印的標籤對不上。' },
    ],
    'project-material': [
      { sel: '#tabbody .card', title: '叫料計算', text: '依色號 × 板厚彙總片數、才數、封邊條公尺數，直接拿去叫板材。色號「-」表示有板材沒填色號。' },
      { sel: '#tabbody .card:last-child', title: '五金彙總', text: '五金與加工項目依類別、名稱加總數量。' },
    ],
    customers: [
      { sel: '#stm', title: '客戶對帳單', text: '選客戶與月份，依交貨日或訂貨日列出該月訂單與計價總額（含折數、加工費、稅），可列印。' },
      { sel: '#newc', title: '建立客戶', text: '客戶編號（例 AA0B001）、設計師/業務名稱、電話、公司、統編、板材折數、安裝折數。折數會套進該客戶專案的計價。' },
    ],
    feedback: [
      { sel: '#app .tabs', title: '回饋清單', text: '操作者從右下角「意見回饋」送出的內容都在這裡，依狀態分頁：新 → 已排程 → 已完成／不處理。' },
      { sel: '#app .tablewrap', title: '處理', text: '類型、狀態、修正版本、處理備註都可直接改。「附件」欄可點開操作者附的截圖／檔案，也能按 ＋ 補附件。狀態改成「已完成」會自動填目前版本，並出現在操作者看的「更新通知」。' },
      { sel: '#app .card .row button', title: '交給開發者', text: '按「匯出待處理清單」會下載一份 Markdown（含附件連結），整段貼給開發者（Claude）就能依序處理，處理完回來改狀態。' },
    ],
    updates: [
      { sel: '#updtabs', title: '更新通知', text: '三個分頁：「針對回饋的修正」依版本列出哪些回饋已修好；「處理中」是收到但還沒改完的；「完整更新紀錄」是每一版的全部變更。' },
      { sel: '#navupd', title: '紅點提醒', text: '系統升級到新版本時，這裡會亮紅點並跳一次提示，進來看過就消失。看到自己回報的項目出現在「已修正」，記得按 Ctrl+F5 重新整理後試試。' },
    ],
    master: [
      { sel: '#app .tabs', title: '基礎資料分頁', text: '色號/單價、零件目錄、櫃體範本（新增櫃體時的標準板件與尺寸公式，標準櫃/水槽櫃/油機吊櫃可自訂）、加工/封邊、標記、五金配件（含進銷貨）、廠商、下拉清單、牌價表、成本分析、公司資料。' },
      { sel: '#mbody', title: '直接在表格裡改', text: '色號頁是「色號 × 板厚」單價矩陣，格子改完即存、清空即刪；最上面綠色列是新增。右上可下載 CSV 整批改完再匯入。標記、五金、廠商也一樣可改可刪；零件目錄可新增或移除名稱。' },
    ],
  };

  let cur = null;  // {name, steps, i}

  function ensureUI() {
    if (document.getElementById('tour-box')) return;
    const box = document.createElement('div'); box.id = 'tour-box';
    const card = document.createElement('div'); card.id = 'tour-card';
    document.body.append(box, card);
  }

  async function show(i) {
    const steps = cur.steps;
    if (i < 0 || i >= steps.length) return end();
    cur.i = i;
    const token = cur;                       // 導覽在等待期間被結束/換頁時，不再把卡片畫回來
    const s = steps[i];
    const el = document.querySelector(s.sel);
    if (!el) return i + 1 < steps.length ? show(i + 1) : end();
    el.scrollIntoView({ block: 'center', behavior: 'instant' });
    await new Promise((r) => setTimeout(r, 120));
    if (cur !== token) return;
    const r0 = el.getBoundingClientRect();
    // 比視窗還高的元素 (大表格) 只框視窗內看得到的部分；一般元素用原本的位置
    const tall = r0.height > window.innerHeight - 200;
    const r = tall
      ? { left: r0.left, width: r0.width, top: Math.max(r0.top, 56), bottom: Math.min(r0.bottom, window.innerHeight - 150) }
      : { left: r0.left, width: r0.width, top: r0.top, bottom: r0.bottom };
    r.height = Math.max(r.bottom - r.top, 24);
    const box = document.getElementById('tour-box'), card = document.getElementById('tour-card');
    box.style.display = 'block';
    Object.assign(box.style, { left: r.left - 6 + 'px', top: r.top - 6 + 'px', width: r.width + 12 + 'px', height: r.height + 12 + 'px' });
    card.style.display = 'block';
    card.innerHTML = `<div class="tour-title">${s.title} <span class="muted">(${i + 1}/${steps.length})</span></div><div>${s.text}</div>
      <div class="tour-btns"><button id="tour-prev" ${i === 0 ? 'disabled' : ''}>上一步</button><button id="tour-next" class="primary">${i === steps.length - 1 ? '完成' : '下一步'}</button><button id="tour-skip" class="link">略過</button></div>`;
    const ch = card.offsetHeight, cw = card.offsetWidth;
    let top = r.bottom + 14, left = Math.min(Math.max(12, r.left), window.innerWidth - cw - 12);
    if (top + ch > window.innerHeight - 12) top = Math.max(12, r.top - ch - 14);
    Object.assign(card.style, { top: top + 'px', left: left + 'px' });
    card.querySelector('#tour-prev').onclick = () => show(i - 1);
    card.querySelector('#tour-next').onclick = () => show(i + 1);
    card.querySelector('#tour-skip').onclick = end;
  }

  function end() {
    const box = document.getElementById('tour-box'), card = document.getElementById('tour-card');
    if (box) box.style.display = 'none';
    if (card) card.style.display = 'none';
    if (cur) { try { localStorage.setItem('tour-done-' + cur.name, '1'); } catch (e) { /* ignore */ } }
    cur = null;
  }

  window.startTour = function (name) {
    const steps = TOURS[name];
    if (!steps) return false;
    ensureUI();
    document.querySelector('.tour-hint')?.remove();
    cur = { name, steps, i: 0 };
    show(0);
    return true;
  };
  window.endTour = end;
  window.hasTour = (name) => !!TOURS[name];

  // 第一次進入該頁 (或分頁) 時提示一次
  window.maybeAutoTour = function (name) {
    document.querySelector('.tour-hint')?.remove();
    if (!TOURS[name] || cur) return;
    let done = false;
    try { done = !!localStorage.getItem('tour-done-' + name); } catch (e) { done = true; }
    if (done) return;
    const bar = document.createElement('div'); bar.className = 'tour-hint';
    bar.innerHTML = `第一次用這一頁？<button class="primary" id="tour-go">看導覽</button><button class="link" id="tour-no">不用了</button>`;
    document.body.appendChild(bar);
    bar.querySelector('#tour-go').onclick = () => { bar.remove(); window.startTour(name); };
    bar.querySelector('#tour-no').onclick = () => { bar.remove(); try { localStorage.setItem('tour-done-' + name, '1'); } catch (e) { /* ignore */ } };
  };

  window.addEventListener('resize', () => cur && show(cur.i));
  window.addEventListener('keydown', (e) => { if (cur && e.key === 'Escape') end(); });
  window.addEventListener('hashchange', () => { if (cur) end(); });
})();
