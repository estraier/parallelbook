"use strict";

export function renderParallelBook(
  selectorElementId, contentElementId, bookList, bookParamName, modeParamName) {
  const queryBookId = getQueryParamValue(bookParamName);
  const queryMode = getQueryParamValue(modeParamName);
  if (selectorElementId && selectorElementId.length > 0) {
    renderSelector(selectorElementId, contentElementId, bookList, bookParamName, modeParamName);
  }
  if (queryBookId) {
    const book = bookList[queryBookId];
    if (book) {
      loadAndRenderParallelBook(contentElementId, queryBookId, book[1], queryMode);
    }
  }
  setGlobalKeyEvents();
}

function getQueryParamValue(paramName) {
  const params = new URLSearchParams(window.location.search);
  return params.get(paramName);
}

function updateUrlParam(paramName, paramValue) {
  const url = new URL(window.location);
  url.searchParams.set(paramName, paramValue);
  history.pushState({}, '', url);
}

function renderSelector(
  selectorElementId, contentElementId, bookList, bookParamName, modeParamName) {
  const queryBookId = getQueryParamValue(bookParamName);
  const queryMode = getQueryParamValue(modeParamName);
  const selectorEl = document.getElementById(selectorElementId);
  if (!selectorEl) {
    console.error(`No container element: ${selectorElementId}`);
    return;
  }
  selectorEl.className = "parallel-book-navi";
  selectorEl.innerHTML = "";
  const firstRow = document.createElement("div");
  firstRow.className = "navi-first-row";
  const bookSelect = document.createElement("select");
  bookSelect.id = selectorElementId + "-book";
  const bookDefaultOption = document.createElement("option");
  bookDefaultOption.value = "";
  bookDefaultOption.textContent = "-- 書籍選択 --";
  bookSelect.appendChild(bookDefaultOption);
  for (const [key, [name]] of Object.entries(bookList)) {
    const option = document.createElement("option");
    option.value = key;
    option.textContent = name;
    if (key === queryBookId) {
      option.selected = true;
    }
    bookSelect.appendChild(option);
  }
  const fileOption = document.createElement("option");
  fileOption.value = "__file__";
  fileOption.textContent = "（JSONファイル）"
  if (queryBookId === fileOption.value) {
    fileOption.selected = true;
  }
  bookSelect.appendChild(fileOption);
  firstRow.appendChild(bookSelect);
  const modeSelect = document.createElement("select");
  modeSelect.id = selectorElementId + "-mode";
  const modes = [
    ["both", "英日併記"],
    ["en", "英語のみ"],
    ["ja", "日本語のみ"]
  ];
  for (const [value, label] of modes) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    if (value === queryMode) {
      option.selected = true;
    }
    modeSelect.appendChild(option);
  }
  firstRow.appendChild(modeSelect);
  selectorEl.appendChild(firstRow);
  bookSelect.addEventListener("change", () => {
    if (!bookSelect.value || bookSelect.value.length == 0) return;
    updateFileInput(selectorElementId, contentElementId);
    if (bookSelect.value === fileOption.value) {
      updateUrlParam(bookParamName, fileOption.value);
      updateFileInput(selectorElementId, contentElementId, true);
    } else {
      updateFileInput(selectorElementId, contentElementId, false);
      const book = bookList[bookSelect.value];
      if (book) {
        updateUrlParam(bookParamName, bookSelect.value);
        loadAndRenderParallelBook(contentElementId, bookSelect.value, book[1], modeSelect.value);
      }
    }
  });
  modeSelect.addEventListener("change", () => {
    const mode = modeSelect.value;
    const contentRoot = document.getElementById(contentElementId);
    if (!contentRoot) return;
    const parallelBlocks = contentRoot.querySelectorAll(".parallel");
    for (const block of parallelBlocks) {
      setParallelBlockMode(block, mode);
    }
    updateUrlParam(modeParamName, modeSelect.value);
  });
  const isFile = bookSelect.value === fileOption.value
  updateFileInput(selectorElementId, contentElementId, isFile);
}

function updateFileInput(selectorElementId, contentElementId, show) {
  const selectorEl = document.getElementById(selectorElementId);
  if (!selectorEl) {
    console.error(`No container element: ${selectorElementId}`);
    return;
  }
  const oldRow = selectorEl.querySelector('.file-row');
  if (oldRow) {
    oldRow.remove(oldRow);
  }
  if (!show) return;
  const row = document.createElement("div");
  row.className = "file-row";
  const fileInput = document.createElement("input");
  fileInput.type = "file";
  fileInput.accept = ".json";
  fileInput.id = selectorElementId + "-file";
  row.appendChild(fileInput);
  selectorEl.appendChild(row);
  fileInput.addEventListener("change", function (event) {
    const modeSelect = document.getElementById(selectorElementId + "-mode");
    const mode = modeSelect ? modeSelect.value : "both";
    const file = event.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = function (e) {
      try {
        const result = e.target.result;
        const bookId = hashString(result);
        const bookContent = JSON.parse(result);
        renderParallelBookContent(contentElementId, bookId, bookContent, mode);
      } catch (err) {
        console.error("JSON error")
      }
    };
    reader.readAsText(file);
  });
}

function hashString(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = (hash << 5) - hash + str.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash).toString(36);
}

async function loadAndRenderParallelBook(contentElementId, bookId, bookUrl, mode) {
  let response = null;
  try {
    response = await fetch(bookUrl);
  } catch(error) {
    console.error(`Fetch error: url=${bookUrl}, error=${error}`)
    return
  }
  if (!response.ok) {
    console.error(`Response error: url=${bookUrl}, status=${response.status}`)
    return;
  }
  let bookContent = null;
  try {
    bookContent = await response.json();
    if (bookContent.format !== "parallel") {
      console.error(`JSON error: url=${bookUrl}, error=not parallel`)
      return
    }
  } catch(error) {
    console.error(`JSON error: url=${bookUrl}, error=${error}`)
    return
  }
  renderParallelBookContent(contentElementId, bookId, bookContent, mode);
}

function setGlobalKeyEvents() {
  document.lastFocused = null;
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Tab") return;
    const active = document.activeElement;
    const bodyOrNull = (active === document.body || active === null);
    if (bodyOrNull && document.lastFocused) {
      event.preventDefault();
      document.lastFocused.focus();
    }
  });
  document.lastInteractionWasKeyboard = false;
  document.addEventListener('keydown', () => {
    document.lastInteractionWasKeyboard = true;
  });
  document.addEventListener('mousedown', () => {
    document.lastInteractionWasKeyboard = false;
  });
  document.addEventListener("click", (e) => {
    let el = e.target;
    while (el && el !== document.body) {
      if (el.tagName.toLowerCase() === "a" && el.getAttribute("href")?.startsWith("#chapter-")) {
        const targetId = el.getAttribute("href").substring(1);
        const target = document.getElementById(targetId);
        if (target) {
          setTimeout(() => target.focus({ preventScroll: true }), 0);
        }
        break;
      }
      el = el.parentElement;
    }
  });
}

function toggleParallelBlock(block) {
  const spanEn = block.querySelector('span[lang="en"]');
  const spanJa = block.querySelector('span[lang="ja"]');
  const spanAn = block.querySelector('.analysis');
  if (block.lang === "ja") {
    if (spanEn) {
      if (spanEn.style.display === "none") {
        spanEn.style.display = "";
      } else {
        spanEn.style.display = "none";
      }
    }
  } else {
    if (spanJa) {
      if (spanAn) {
        if (spanJa.style.display === "none") {
          spanJa.style.display = "";
        } else if (spanAn.style.display === "none") {
          spanAn.style.display = "";
        } else {
          spanJa.style.display = "none";
          spanAn.style.display = "none";
        }
      } else {
        if (spanJa.style.display === "none") {
          spanJa.style.display = "";
        } else {
          spanJa.style.display = "none";
        }
      }
    }
  }
}

function utterParallelBlock(block) {
  if (!SpeechSynthesisUtterance) return;
  speechSynthesis.cancel();
  const spanEn = block.querySelector('span[lang="en"]');
  const spanJa = block.querySelector('span[lang="ja"]');
  if (block.lang === "ja" && spanEn.style.display === "none") {
    const jaText = spanJa.textContent.trim();
    if (jaText) {
      const utterance = new SpeechSynthesisUtterance(jaText);
      utterance.lang = "ja-JP";
      speechSynthesis.speak(utterance);
    }
  } else {
    const enText = spanEn.textContent.trim();
    if (enText) {
      const utterance = new SpeechSynthesisUtterance(enText);
      utterance.lang = "en-US";
      speechSynthesis.speak(utterance);
    }
  }
}

function createStyledSentenceFragment(sentence) {
  const contractionTable = {
    "have": ["ve"], "has": ["s"], "had": ["d"], "am": ["m"], "are": ["re"], "is": ["s"],
    "would": ["d"], "will": ["ll"], "shall": ["ll"], "did": ["d"],
  };
  const phrasalParticles = [
    "up","out","down","through","off","in","on","over","back","away","apart",
    "along","about","across","around","under","by","forth","together"
  ];
  function tokenize(s) {
    return Array.from(s.matchAll(/[A-Za-z0-9]+|\s+|[^A-Za-z0-9\s]/g)).map(m => m[0]);
  }
  function expandElements(elements, contractionTable) {
    const expanded = [];
    elements.forEach((el, idx) => {
      const groupId = idx + "_grp";
      expanded.push({ ...el, _groupId: groupId });
      for (const [key, forms] of Object.entries(contractionTable)) {
        const re = new RegExp("^(?:" + key + ")(?=\\s|$)", "i");
        if (el.text && re.test(el.text)) {
          forms.forEach(contr => {
            ["'", "’"].forEach(apos => {
              const replaced = el.text.replace(re, apos + contr);
              expanded.push({ ...el, text: replaced, _groupId: groupId });
            });
          });
        }
      }
    });
    return expanded;
  }
  function normalizePhrase(s) {
    let norm = s.normalize('NFKC').toLowerCase();
    norm = norm
      .replace(/[`＇‘’]/g, "'")
      .replace(/[“”]/g, '"');
    return norm;
  }
  const tokens = tokenize(sentence.text);
  let elementPool = expandElements(sentence.elements, contractionTable);
  const usedGroupIds = new Set();
  let i = 0;
  const frag = document.createDocumentFragment();
  let reservedParticles = [];
  while (i < tokens.length) {
    const token = tokens[i];
    if (/^\s+$/.test(token)) {
      frag.append(token);
      i++;
      continue;
    }
    if (reservedParticles.length && normalizePhrase(token) === normalizePhrase(reservedParticles[0].token)) {
      const span = document.createElement("span");
      span.className = `element element-v`;
      span.setAttribute("data-type", "V");
      span.textContent = token;
      frag.appendChild(span);
      reservedParticles.shift();
      i++;
      continue;
    }
    let matched = null, matchedLen = 0, matchedGroupId = null;
    for (let eIdx = 0; eIdx < elementPool.length; ++eIdx) {
      const el = elementPool[eIdx];
      if (usedGroupIds.has(el._groupId)) continue;
      const elTokens = tokenize(el.text);
      const window = tokens.slice(i, i + elTokens.length);
      if (
        window.length === elTokens.length &&
        normalizePhrase(window.join("")) === normalizePhrase(elTokens.join(""))
      ) {
        matched = el;
        matchedLen = elTokens.length;
        matchedGroupId = el._groupId;
        break;
      }
    }
    if (!matched) {
      for (let eIdx = 0; eIdx < elementPool.length; ++eIdx) {
        const el = elementPool[eIdx];
        if (el.type !== "V" || usedGroupIds.has(el._groupId)) continue;
        const normElText = normalizePhrase(el.text);
        const match = normElText.match(/^(do|does|did|will|would|should|have|has|had|can|could|may|might|must|shall|is|are|was|were|am|don't|doesn't|didn't|won't|can't|isn't|aren't|wasn't|weren't|shouldn't|wouldn't|couldn't|haven't|hasn't|hadn't|mustn't|n't)\b(.*)/i);
        if (match) {
          const modal = match[1];
          const rest = match[2].trim();
          const tokenNorm = normalizePhrase(tokens[i]);
          if (tokenNorm === modal) {
            matched = {
              ...el,
              _groupId: el._groupId + "_modal_only",
              text: tokens[i],
              type: el.type
            };
            matchedLen = 1;
            matchedGroupId = matched._groupId;
            if (rest) {
              elementPool.splice(
                eIdx + 1, 0,
                {
                  ...el,
                  text: rest,
                  _groupId: el._groupId + "_rest"
                }
              );
            }
            break;
          }
        }
      }
    }
    if (!matched) {
      for (let eIdx = 0; eIdx < elementPool.length; ++eIdx) {
        const el = elementPool[eIdx];
        if (el.type !== "V" || usedGroupIds.has(el._groupId)) continue;
        for (const particle of phrasalParticles) {
          const suffix = " " + particle;
          if (
            el.text.toLowerCase().endsWith(suffix) &&
            el.text.length > suffix.length
          ) {
            const baseVerb = el.text.slice(0, el.text.length - suffix.length);
            const baseTokens = tokenize(baseVerb);
            const windowTokens = tokens.slice(i, i + baseTokens.length + 4);
            if (
              windowTokens.length >= baseTokens.length + 1 &&
              normalizePhrase(windowTokens.slice(0, baseTokens.length).join("")) === normalizePhrase(baseTokens.join(""))
            ) {
              for (let j = baseTokens.length; j < windowTokens.length; ++j) {
                if (normalizePhrase(windowTokens[j]) === normalizePhrase(particle)) {
                  matched = {
                    ...el,
                    text: baseVerb,
                    _groupId: el._groupId + "_phrasal",
                  };
                  matchedLen = baseTokens.length;
                  matchedGroupId = matched._groupId;
                  reservedParticles.push({ token: windowTokens[j], type: el.type });
                  break;
                }
              }
            }
          }
          if (matched) break;
        }
        if (matched) break;
      }
    }
    if (matched) {
      const span = document.createElement("span");
      span.className = `element element-${matched.type.toLowerCase()}`;
      span.setAttribute("data-type", matched.type);
      span.textContent = tokens.slice(i, i + matchedLen).join("");
      frag.appendChild(span);
      usedGroupIds.add(matchedGroupId);
      i += matchedLen;
    } else {
      frag.append(token);
      i++;
    }
  }
  return frag;
}

function createAnalysisSentenceItem(sentence, className, level, source) {
  const sentenceLi = document.createElement("li");
  sentenceLi.className = className;
  if (sentence.pattern && sentence.pattern.length > 0) {
    const patternSpan = document.createElement("span");
    patternSpan.className = "pattern pattern-" + sentence.pattern.toLowerCase();
    patternSpan.textContent = sentence.pattern;
    sentenceLi.appendChild(patternSpan);
  }
  if (sentence.relation && sentence.relation.length > 0) {
    const relationSpan = document.createElement("span");
    relationSpan.className = "relation";
    relationSpan.textContent = sentence.relation;
    sentenceLi.appendChild(relationSpan);
  }
  if (sentence.text && sentence.text.length > 0) {
    const textSpan = document.createElement("span");
    textSpan.className = "text";
    textSpan.appendChild(createStyledSentenceFragment(sentence));
    sentenceLi.appendChild(textSpan);
  }
  if (sentence.elements && sentence.elements.length > 0) {
    const elementsUl = document.createElement("ul");
    elementsUl.className = "element-list";
    for (const element of sentence.elements) {
      const elementLi = document.createElement("li");
      elementLi.className = "element-item";
      if (element.type && element.type.length > 0) {
        const elementTypeSpan = document.createElement("span");
        elementTypeSpan.className = "type type-" + element.type.toLowerCase();
        elementTypeSpan.textContent = element.type;
        elementLi.appendChild(elementTypeSpan);
      }
      if (element.text && element.text.length > 0) {
        const elementTextSpan = document.createElement("text");
        elementTextSpan.className = "text";
        elementTextSpan.textContent = element.text;
        elementLi.appendChild(elementTextSpan);
      }
      if (element.translation && element.translation.length > 0) {
        const tranSpan = document.createElement("span");
        tranSpan.className = "tran";
        tranSpan.textContent = element.translation;
        elementLi.appendChild(tranSpan);
      }
      const verb_attrs = [
        [element.tense, {"past": "過去"}],
        [element.aspect, {"progressive": "進行", "perfect": "完了", "perfect progressive": "完進"}],
        [element.mood, {"imperative": "命令", "subjunctive": "仮定", "conditional": "条件"}],
        [element.voice, {"passive": "受動"}],
      ];
      for (const verb_attr of verb_attrs) {
        const label = verb_attr[1][verb_attr[0]];
        if (label) {
          const vattrSpan = document.createElement("span");
          vattrSpan.className = "vattr";
          vattrSpan.textContent = label;
          elementLi.appendChild(vattrSpan);
        }
      }
      if (element.subclauses && element.subclauses.length > 0 && level < 2) {
        const subclausesUl = document.createElement("ul");
        subclausesUl.className = "subclause-list";
        for (const subclause of element.subclauses) {
          subclausesUl.appendChild(createAnalysisSentenceItem(
            subclause, "clause", level + 1, source));
        }
        elementLi.appendChild(subclausesUl);
      }
      elementsUl.appendChild(elementLi);
    }
    sentenceLi.appendChild(elementsUl);
  }
  if (sentence.subsentences && sentence.subsentences.length > 0 && level < 2) {
    const subsentencesUl = document.createElement("ul");
    subsentencesUl.className = "subsentence-list";
    for (const subsentence of sentence.subsentences) {
      subsentencesUl.appendChild(createAnalysisSentenceItem(
        subsentence, "sentence", level + 1, source));
    }
    sentenceLi.appendChild(subsentencesUl);
  }
  return sentenceLi;
}

function createAnalysisList(analysis, source) {
  const list = document.createElement("ul");
  list.className = "analysis";
  for (const sentence of analysis) {
    list.appendChild(createAnalysisSentenceItem(sentence, "sentence", 1, source));
  }
  return list;
}

function createParallelBlock(tagName, className, source, target, mode, analysis) {
  const block = document.createElement(tagName);
  block.className = `${className} parallel`;
  block.setAttribute("role", "group");
  block.setAttribute("tabindex", "0");
  const spanEn = document.createElement("span");
  spanEn.lang = "en";
  spanEn.textContent = source ?? "";
  block.appendChild(spanEn);
  const spanJa = document.createElement("span");
  spanJa.lang = "ja";
  spanJa.textContent = target ?? "";
  block.appendChild(spanJa);

  if (analysis && analysis.length > 0) {
    const analysisBlock = createAnalysisList(analysis, source);

    block.appendChild(analysisBlock);
  }


  const toggle = document.createElement("span");
  toggle.lang = "zxx";
  toggle.className = "parallel-toggle";
  toggle.textContent = "▶";
  toggle.setAttribute("role", "button");
  toggle.setAttribute("aria-hidden", "true");
  block.appendChild(toggle);
  toggle.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    toggleParallelBlock(block);
  });
  toggle.addEventListener("contextmenu", (e) => {
    e.preventDefault();
    e.stopPropagation();
    utterParallelBlock(block);
  });
  block.addEventListener("keydown", (e) => {
    if (e.key === " ") {
      e.preventDefault();
      e.stopPropagation();
      toggleParallelBlock(block);
    }
  });
  block.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      e.stopPropagation();
      utterParallelBlock(block);
    }
  });
  block.addEventListener("focus", () => {
    if (document.lastInteractionWasKeyboard) {
      block.scrollIntoView({
        behavior: "smooth", block: "center"
      });
    }
  });
  block.addEventListener("focusin", () => {
    document.lastFocused = block;
  });
  setParallelBlockMode(block, mode);
  return block;
}

function setParallelBlockMode(block, mode) {
  if (!mode || mode === "both") {
    block.lang = "zxx";
  } else {
    block.lang = mode;
  }
  const spanEn = block.querySelector('span[lang="en"]');
  const spanJa = block.querySelector('span[lang="ja"]');
  const spanAn = block.querySelector('.analysis');
  if (spanEn) {
    spanEn.style.display = (mode === "ja") ? "none" : "";
    if (mode === "ja") {
      spanEn.style.opacity = "0.8";
    } else {
      spanEn.style.opacity = "";
    }
  }
  if (spanJa) {
    spanJa.style.display = (mode === "en") ? "none" : "";
    if (mode === "ja") {
      spanJa.style.opacity = "1";
      spanJa.style.fontSize = "95%";
      spanJa.style.marginLeft = "0";
    } else {
      spanJa.style.opacity = "";
      spanJa.style.fontSize = "";
      spanJa.style.marginLeft = "";
    }
  }
  if (spanAn) {
    spanAn.style.display = "none";
  }
}

function toggleBookmark(pane, bookId) {
  const key = `parallelbook:${bookId}:bookmark`;
  const oldValue = localStorage.getItem(key);
  if (oldValue === pane.id) {
    localStorage.removeItem(key);
  } else {
    localStorage.setItem(key, pane.id);
  }
}

function setParallelPane(pane, bookId, contentEl) {
  pane.id = "pane-" + pane.id.replace(/-\d+$/, "");
  pane.classList.add("pane");
  const mark = document.createElement("span");
  mark.className = "bookmark";
  mark.setAttribute("aria-hidden", "true")
  mark.setAttribute("title", "ブックマーク");
  mark.textContent = "⚑";
  pane.appendChild(mark);
  mark.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    toggleBookmark(pane, bookId);
    renderBookmark(contentEl, bookId);
  });
  if (localStorage) {
    pane.addEventListener("focusin", () => {
      const key = `parallelbook:${bookId}:focus`;
      localStorage.setItem(key, pane.id);
      renderBookmark(contentEl, bookId);
    });
    pane.addEventListener("keydown", (e) => {
      if (e.key === "b") {
        toggleBookmark(pane, bookId);
        renderBookmark(contentEl, bookId);
      }
    });
  }
}

function renderBookmark(contentEl, bookId) {
  if (!localStorage) return;
  const focusKey = `parallelbook:${bookId}:focus`;
  const focusValue = localStorage.getItem(focusKey);
  const bookmarkKey = `parallelbook:${bookId}:bookmark`;
  const bookmarkValue = localStorage.getItem(bookmarkKey);
  for (const pane of contentEl.querySelectorAll(".pane")) {
    const mark = pane.querySelector(".bookmark");
    mark.classList.remove("active-bookmark");
    if (pane.id === bookmarkValue) {
      mark.classList.add("active-bookmark");
    }
  }
  const contentNav = contentEl.querySelector(".content-nav");
  contentNav.innerHTML = "";
  if (focusValue) {
    const anchor = document.createElement("a");
    anchor.href = "#" + focusValue;
    anchor.setAttribute("aria-label", "最後のフォーカスに移動");
    anchor.setAttribute("title", "最後のフォーカスに移動");
    anchor.textContent = "➣";
    contentNav.appendChild(anchor);
  } else {
    const span = document.createElement("span");
    span.setAttribute("aria-hidden", "true");
    span.textContent = "➣";
    contentNav.appendChild(span);
  }
  if (bookmarkValue) {
    const anchor = document.createElement("a");
    anchor.setAttribute("aria-label", "ブックマークに移動");
    anchor.setAttribute("title", "ブックマークに移動");
    anchor.href = "#" + bookmarkValue;
    anchor.textContent = "⚑";
    contentNav.appendChild(anchor);
  } else {
    const span = document.createElement("span");
    span.setAttribute("aria-hidden", "true");
    span.textContent = "️⚑";
    contentNav.appendChild(span);
  }
}

function utterMonolingualBlock(block) {
  if (!SpeechSynthesisUtterance) return;
  speechSynthesis.cancel();
  const text = block.textContent.trim();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "en-US";
  speechSynthesis.speak(utterance);
}

function setMonolingualBlock(block) {
  block.setAttribute("tabindex", "0");
  block.lang = "en";
  block.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      e.stopPropagation();
      utterMonolingualBlock(block);
    }
  });
}

function createTableOfContents(book, mode) {
  const tocNav = document.createElement("nav");
  tocNav.className = "book-toc";
  tocNav.setAttribute("aria-label", "目次");
  const list = document.createElement("ul");
  let num_chapter = 0;
  for (const chapter of book.chapters) {
    num_chapter++;
    const item = document.createElement("li");
    const anchor = document.createElement("a");
    anchor.href = "#chapter-" + num_chapter;
    anchor.className = "toc-item parallel";
    anchor.setAttribute("tabindex", "0");
    let source = "Chapter " + num_chapter;
    let target = "第" + num_chapter + "章";
    if (chapter.title) {
      if (chapter.title.source) {
        source = chapter.title.source;
      }
      if (chapter.title.target) {
        target = chapter.title.target;
      }
    }
    const spanEn = document.createElement("span");
    spanEn.lang = "en";
    spanEn.textContent = source;
    anchor.appendChild(spanEn);
    const spanJa = document.createElement("span");
    spanJa.lang = "ja";
    spanJa.textContent = target;
    anchor.appendChild(spanJa);
    item.appendChild(anchor);
    setParallelBlockMode(item, mode);
    list.appendChild(item);
  }
  tocNav.appendChild(list);
  return tocNav;
}

function renderParallelBookContent(contentElementId, bookId, bookContent, mode) {
  const contentEl = document.getElementById(contentElementId);
  if (!contentEl) {
    console.error(`No container element: ${contentElementId}`);
    return;
  }
  contentEl.className = "parallel-book";
  contentEl.innerHTML = "";
  const contentNav = document.createElement("nav");
  contentNav.className = "content-nav";
  contentNav.setAttribute("aria-label", "コンテンツ内の移動ナビ");
  contentEl.appendChild(contentNav);
  if (bookContent.title) {
    contentEl.appendChild(createParallelBlock(
      "h1", "book-title", bookContent.title.source, bookContent.title.target, mode,
      bookContent.title.analysis));
  }
  if (bookContent.author) {
    contentEl.appendChild(createParallelBlock(
      "div", "book-author", bookContent.author.source, bookContent.author.target, mode,
      bookContent.author.analysis));
  }
  if (bookContent.chapters && bookContent.chapters.length > 1) {
    contentEl.appendChild(createTableOfContents(bookContent, mode));
  }
  let num_chapter = 0;
  for (const chapter of bookContent.chapters ?? []) {
    num_chapter++;
    const chapterSection = document.createElement("section");
    chapterSection.id = "chapter-" + num_chapter;
    chapterSection.className = "chapter";
    chapterSection.setAttribute("tabindex", "-1");
    const chapterNav = document.createElement("nav");
    chapterNav.className = "chapter-nav";
    chapterNav.setAttribute("aria-label", "章による移動ナビ");
    if (num_chapter > 1) {
      const chapterPrev = document.createElement("a")
      chapterPrev.href = "#chapter-" + (num_chapter - 1);
      chapterPrev.setAttribute("aria-label", "前の章に移動");
      chapterPrev.setAttribute("title", "前の章に移動");
      chapterPrev.setAttribute("tabindex", "0");
      chapterPrev.textContent = "⇚";
      chapterNav.appendChild(chapterPrev);
    } else {
      const chapterPrev = document.createElement("span")
      chapterPrev.setAttribute("aria-hidden", "true");
      chapterPrev.textContent = "⇚";
      chapterNav.appendChild(chapterPrev);
    }
    const chapterCurrent = document.createElement("a")
    chapterCurrent.href = "#chapter-" + num_chapter;
    chapterCurrent.setAttribute("aria-label", "この章に移動");
    chapterCurrent.setAttribute("title", "この章に移動");
    chapterCurrent.setAttribute("tabindex", "-1");
    chapterCurrent.textContent = "§";
    chapterNav.appendChild(chapterCurrent);
    if (num_chapter < bookContent.chapters.length) {
      const chapterNext = document.createElement("a");
      chapterNext.href = "#chapter-" + (num_chapter + 1);
      chapterNext.setAttribute("aria-label", "次の章に移動");
      chapterNext.setAttribute("title", "次の章に移動");
      chapterNext.setAttribute("tabindex", "0");
      chapterNext.textContent = "⇛";
      chapterNav.appendChild(chapterNext);
    } else {
      const chapterNext = document.createElement("span");
      chapterNext.setAttribute("aria-hidden", "true");
      chapterNext.textContent = "⇛";
      chapterNav.appendChild(chapterNext);
    }
    chapterSection.appendChild(chapterNav);
    if (chapter.title) {
      const pane = createParallelBlock(
        "h2", "chapter-title", chapter.title.source, chapter.title.target, mode,
        chapter.title.analysis);
      pane.id = chapter.title.id;
      chapterSection.appendChild(pane);
      setParallelPane(pane, bookId, contentEl);
    }
    for (const block of chapter.body ?? []) {
      if (block.paragraph) {
        const pane = document.createElement("p");
        pane.className = "paragraph"
        for (const item of block.paragraph) {
          if (!pane.id) pane.id = item.id;
          pane.appendChild(createParallelBlock(
            "span", "sentence", item.source, item.target, mode, item.analysis));
        }
        chapterSection.appendChild(pane);
        setParallelPane(pane, bookId, contentEl);
      } else if (block.blockquote) {
        const pane = document.createElement("blockquote");
        pane.className = "blockquote"
        for (const item of block.blockquote) {
          if (!pane.id) pane.id = item.id;
          pane.appendChild(createParallelBlock(
            "span", "sentence", item.source, item.target, mode, item.analysis));
        }
        chapterSection.appendChild(pane);
        setParallelPane(pane, bookId, contentEl);
      } else if (block.header) {
        const pane = createParallelBlock(
          "h3", "header", block.header.source, block.header.target, mode, block.header.analysis);
        pane.id = block.header.id;
        chapterSection.appendChild(pane);
        setParallelPane(pane, bookId, contentEl);
      } else if (block.list) {
        const pane = document.createElement("ul");
        pane.className = "list"
        for (const item of block.list) {
          if (!pane.id) pane.id = item.id;
          const li = document.createElement("li");
          li.appendChild(createParallelBlock(
            "span", "list-item", item.source, item.target, mode, item.analysis));
          pane.appendChild(li);
        }
        chapterSection.appendChild(pane);
        setParallelPane(pane, bookId, contentEl);
      } else if (block.table) {
        const pane = document.createElement("table");
        pane.className = "table"
        for (const row of block.table) {
          const tr = document.createElement("tr");
          for (const cell of row) {
            if (!pane.id) pane.id = cell.id;
            const td = document.createElement("td");
            td.appendChild(createParallelBlock(
              "span", "table-cell", cell.source, cell.target, mode, cell.analysis));
            tr.appendChild(td);
          }
          pane.appendChild(tr);
        }
        chapterSection.appendChild(pane);
        setParallelPane(pane, bookId, contentEl);
      } else if (block.code) {
        const pane = document.createElement("pre");
        pane.className = "code mono";
        pane.textContent = block.code.text;
        chapterSection.appendChild(pane);
        setMonolingualBlock(pane);
      } else if (block.macro?.name === "image") {
        const values = (block.macro.value ?? "").trim().split(" ");
        const pane = document.createElement("div");
        pane.className = "macro-image"
        const img = document.createElement("img");
        img.src = values[0];
        if (values.length > 0) {
          img.alt = values.slice(1).join(" ");
        }
        pane.appendChild(img);
        chapterSection.appendChild(pane);
      }
    }
    contentEl.appendChild(chapterSection);
  }
  contentEl.appendChild(createMetadataPane(bookContent));
  renderBookmark(contentEl, bookId);
}

function createMetadataPane(bookContent) {
  const pane = document.createElement("aside");
  pane.lang = "ja";
  pane.className = "book-meta";
  const counts = countSourceWordsInBook(bookContent);
  const blockCountSpan = document.createElement("span");
  blockCountSpan.textContent = `段数: ${counts.blocks}`;
  pane.appendChild(blockCountSpan);
  const sentenceCountSpan = document.createElement("span");
  sentenceCountSpan.textContent = `文数: ${counts.sentences}`;
  pane.appendChild(sentenceCountSpan);
  const wordCountSpan = document.createElement("span");
  wordCountSpan.textContent = `単語数: ${counts.words}`;
  pane.appendChild(wordCountSpan);
  const characterCountSpan = document.createElement("span");
  characterCountSpan.textContent = `文字数: ${counts.characters}`;
  pane.appendChild(characterCountSpan);
  return pane;
}

function countSourceWordsInBook(bookContent) {
  const counts = {
    blocks: 0,
    sentences: 0,
    words: 0,
    characters: 0,
  }
  function addCounts(text) {
    if (!text) return;
    counts.sentences += 1
    const matches = text.match(/\b[\w\u2019']+\b/g);
    if (matches) {
      counts.words += matches.length;
    }
    counts.characters += text.length;
  }
  if (bookContent.title?.source) {
    addCounts(bookContent.title.source);
    counts.blocks += 1;
  }
  if (bookContent.author?.source) {
    addCounts(bookContent.author.source);
    counts.blocks += 1;
  }
  for (const chapter of bookContent.chapters ?? []) {
    if (chapter.title?.source) {
      addCounts(chapter.title.source);
      counts.blocks += 1;
    }
    for (const block of chapter.body ?? []) {
      if (block.paragraph) {
        for (const item of block.paragraph) {
          addCounts(item.source);
        }
        counts.blocks += 1;
      } else if (block.blockquote) {
        for (const item of block.blockquote) {
          addCounts(item.source);
        }
        counts.blocks += 1;
      } else if (block.header?.source) {
        addCounts(block.header.source);
        counts.blocks += 1;
      } else if (block.list) {
        for (const item of block.list) {
          addCounts(item.source);
        }
        counts.blocks += 1;
      } else if (block.table) {
        for (const row of block.table) {
          for (const cell of row) {
            addCounts(cell.source);
          }
        }
        counts.blocks += 1;
      } else if (block.code) {
        addCounts(block.code.text);
        counts.blocks += 1;
      }
    }
  }
  return counts;
}
