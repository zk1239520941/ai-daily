/** AI Daily 页面交互：阅读进度、滚动显现、首页加载更多、归档日历、搜索 */
(function () {
  var bar = document.getElementById("reading-progress");
  if (bar) {
    /** @param {void} _ */
    function updateProgress() {
      var doc = document.documentElement;
      var scrollTop = doc.scrollTop || document.body.scrollTop;
      var height = doc.scrollHeight - doc.clientHeight;
      bar.style.width = (height > 0 ? (scrollTop / height) * 100 : 0) + "%";
    }
    window.addEventListener("scroll", updateProgress, { passive: true });
    updateProgress();
  }

  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    document.querySelectorAll(".reveal").forEach(function (el) {
      el.classList.add("is-visible");
    });
  } else {
    var revealItems = document.querySelectorAll(".reveal");
    if (revealItems.length && "IntersectionObserver" in window) {
      var observer = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            if (entry.isIntersecting) {
              entry.target.classList.add("is-visible");
              observer.unobserve(entry.target);
            }
          });
        },
        /* 手机上栏目标题区很高，阈值过严会导致整栏永远不显现 */
        { threshold: 0.01, rootMargin: "0px 0px -4% 0px" }
      );

      revealItems.forEach(function (el) {
        observer.observe(el);
      });

      /* 兜底：首屏已在视口内的元素若未触发，强制显现 */
      window.setTimeout(function () {
        revealItems.forEach(function (el) {
          if (el.classList.contains("is-visible")) return;
          var rect = el.getBoundingClientRect();
          if (rect.top < window.innerHeight && rect.bottom > 0) {
            el.classList.add("is-visible");
            observer.unobserve(el);
          }
        });
      }, 400);
    } else {
      revealItems.forEach(function (el) {
        el.classList.add("is-visible");
      });
    }
  }

  document
    .querySelectorAll(".entry-figure img, .article-cover img, .issue-card__cover img")
    .forEach(function (img) {
      img.addEventListener("error", function () {
        var figure = img.closest("figure") || img.closest(".issue-card__cover");
        if (figure) {
          figure.classList.add("is-hidden");
          figure.style.display = "none";
        }
      });
    });

  var tocLinks = document.querySelectorAll(".article-toc__link");
  var boardSections = document.querySelectorAll(".board-section[id]");
  if (tocLinks.length && boardSections.length && "IntersectionObserver" in window) {
    var activeId = "";

    function setActive(id) {
      if (!id || id === activeId) return;
      activeId = id;
      tocLinks.forEach(function (link) {
        var href = link.getAttribute("href") || "";
        link.classList.toggle("is-active", href === "#" + id);
      });
    }

    var sectionObserver = new IntersectionObserver(
      function (entries) {
        var visible = entries
          .filter(function (entry) {
            return entry.isIntersecting;
          })
          .sort(function (a, b) {
            return a.boundingClientRect.top - b.boundingClientRect.top;
          });
        if (visible.length) {
          setActive(visible[0].target.id);
        }
      },
      { rootMargin: "-20% 0px -55% 0px", threshold: 0.01 }
    );

    boardSections.forEach(function (section) {
      sectionObserver.observe(section);
    });

    if (boardSections[0]) {
      setActive(boardSections[0].id);
    }
  }

  /** 读取嵌入的 JSON 数据块 */
  function readJsonScript(id) {
    var node = document.getElementById(id);
    if (!node) return null;
    try {
      return JSON.parse(node.textContent || "");
    } catch (e) {
      return null;
    }
  }

  /** 渲染普通索引卡片 HTML */
  function renderIssueCard(issue, index) {
    var metaBits = [];
    if (issue.entries) metaBits.push(issue.entries + " 条精选");
    if (issue.sections) metaBits.push(issue.sections);
    var footer = metaBits.join(" · ");
    if (footer) footer += " · 阅读全文 →";
    else footer = "阅读全文 →";
    var cover = issue.cover
      ? '<div class="issue-card__cover"><img src="' +
        issue.cover +
        '" alt="" loading="lazy" referrerpolicy="no-referrer" decoding="async"/></div>'
      : "";
    return (
      '<article class="issue-card reveal" style="--i:' +
      index +
      '">' +
      cover +
      '<div class="issue-meta">' +
      '<span class="issue-no">第 ' +
      String(issue.issue_no).padStart(3, "0") +
      " 期</span>" +
      '<span class="issue-date">' +
      issue.date +
      (issue.time ? " · " + issue.time : "") +
      "</span>" +
      '<span class="issue-badge">' +
      issue.profile +
      "</span>" +
      "</div>" +
      '<h2><a href="' +
      issue.url +
      '">' +
      escapeHtml(issue.title) +
      "</a></h2>" +
      '<p class="issue-excerpt">' +
      escapeHtml(issue.excerpt) +
      "</p>" +
      '<div class="issue-footer">' +
      escapeHtml(footer) +
      "</div>" +
      "</article>"
    );
  }

  function escapeHtml(text) {
    var div = document.createElement("div");
    div.textContent = text || "";
    return div.innerHTML;
  }

  /** 首页「加载更多」：按年 fetch issues-YYYY.json */
  function initLoadMore() {
    var wrap = document.getElementById("load-more-wrap");
    var grid = document.getElementById("issue-grid");
    var btn = document.getElementById("load-more-btn");
    var indexData = readJsonScript("issues-index-data");
    if (!wrap || !grid || !btn || !indexData) return;

    var shown = parseInt(wrap.getAttribute("data-shown") || "30", 10);
    var total = parseInt(wrap.getAttribute("data-total") || "0", 10);
    var years = indexData.years || [];
    var yearCache = {};
    var yearOffsets = {};
    years.forEach(function (year, i) {
      yearOffsets[year] = i === 0 ? shown : 0;
    });

    function hideButton() {
      wrap.style.display = "none";
    }

    if (shown >= total) {
      hideButton();
      return;
    }

    function fetchYear(year) {
      if (yearCache[year]) return Promise.resolve(yearCache[year]);
      return fetch("news-data/issues-" + year + ".json")
        .then(function (res) {
          if (!res.ok) throw new Error("fetch failed");
          return res.json();
        })
        .then(function (data) {
          yearCache[year] = data;
          return data;
        });
    }

    btn.addEventListener("click", function () {
      btn.disabled = true;
      btn.textContent = "加载中…";

      function appendFromYear(yearIndex) {
        if (shown >= total) {
          hideButton();
          btn.disabled = false;
          return Promise.resolve();
        }
        if (yearIndex >= years.length) {
          hideButton();
          btn.disabled = false;
          btn.textContent = "加载更多";
          return Promise.resolve();
        }
        var year = years[yearIndex];
        return fetchYear(year).then(function (items) {
          var offset = yearOffsets[year] || 0;
          var slice = items.slice(offset, offset + 10);
          yearOffsets[year] = offset + slice.length;
          slice.forEach(function (issue, i) {
            grid.insertAdjacentHTML(
              "beforeend",
              renderIssueCard(issue, shown + i)
            );
          });
          shown += slice.length;
          wrap.setAttribute("data-shown", String(shown));
          document.querySelectorAll(".issue-grid .reveal:not(.is-visible)").forEach(function (el) {
            el.classList.add("is-visible");
          });
          btn.textContent = "加载更多";
          btn.disabled = false;
          if (shown >= total) {
            hideButton();
            return;
          }
          if (yearOffsets[year] >= items.length) {
            appendFromYear(yearIndex + 1);
          }
        });
      }

      appendFromYear(0).catch(function () {
        btn.textContent = "加载失败，重试";
        btn.disabled = false;
      });
    });
  }

  /** 归档页 Tab 切换 */
  function initArchiveTabs() {
    var root = document.getElementById("archive-tabs");
    if (!root) return;
    var buttons = root.querySelectorAll(".archive-tabs__btn");
    var panels = root.querySelectorAll(".archive-tabs__panel");

    buttons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var tab = btn.getAttribute("data-tab");
        buttons.forEach(function (b) {
          var active = b === btn;
          b.classList.toggle("is-active", active);
          b.setAttribute("aria-selected", active ? "true" : "false");
        });
        panels.forEach(function (panel) {
          var active = panel.getAttribute("data-panel") === tab;
          panel.classList.toggle("is-active", active);
          panel.hidden = !active;
        });
        if (tab === "calendar") {
          renderArchiveCalendar();
        }
      });
    });

    initArchiveCalendar();
  }

  /** 渲染归档月历 */
  function initArchiveCalendar() {
    var data = readJsonScript("archive-year-data");
    var select = document.getElementById("calendar-month-select");
    var calendar = document.getElementById("archive-calendar");
    if (!data || !select || !calendar) return;

    var year = data.year;
    var months = data.months || {};
    var monthKeys = Object.keys(months).sort();
    if (!monthKeys.length) {
      calendar.innerHTML = '<p class="empty-state">暂无数据</p>';
      return;
    }

    if (!select.options.length) {
      monthKeys.forEach(function (mm) {
        var opt = document.createElement("option");
        opt.value = mm;
        opt.textContent = parseInt(mm, 10) + " 月";
        select.appendChild(opt);
      });
      select.addEventListener("change", renderArchiveCalendar);
    }

    renderArchiveCalendar();

    function renderArchiveCalendar() {
      var mm = select.value || monthKeys[0];
      var days = months[mm] || [];
      var first = new Date(parseInt(year, 10), parseInt(mm, 10) - 1, 1);
      var startWeekday = first.getDay();
      var daysInMonth = new Date(parseInt(year, 10), parseInt(mm, 10), 0).getDate();
      var html = '<div class="archive-calendar__head">';
      ["日", "一", "二", "三", "四", "五", "六"].forEach(function (label) {
        html += '<span class="archive-calendar__dow">' + label + "</span>";
      });
      html += '</div><div class="archive-calendar__grid">';

      for (var i = 0; i < startWeekday; i++) {
        html += '<span class="archive-calendar__cell archive-calendar__cell--empty"></span>';
      }
      for (var d = 1; d <= daysInMonth; d++) {
        var dd = String(d).padStart(2, "0");
        var hasIssue = days.indexOf(dd) !== -1;
        if (hasIssue) {
          html +=
            '<a class="archive-calendar__cell archive-calendar__cell--active" href="' +
            mm +
            ".html#" +
            dd +
            '">' +
            d +
            "</a>";
        } else {
          html +=
            '<span class="archive-calendar__cell">' + d + "</span>";
        }
      }
      html += "</div>";
      calendar.innerHTML = html;
    }
  }

  /** 搜索页：读取全部 issues-YYYY.json 做本地 filter */
  function initSearch() {
    var input = document.getElementById("search-input");
    var results = document.getElementById("search-results");
    var status = document.getElementById("search-status");
    var indexData = readJsonScript("issues-index-data");
    if (!input || !results || !indexData) return;

    var allIssues = null;
    var loading = false;

    function loadAllIssues() {
      if (allIssues) return Promise.resolve(allIssues);
      if (loading) return Promise.resolve([]);
      loading = true;
      var years = indexData.years;
      if (!years) {
        return fetch("news-data/issues-index.json")
          .then(function (res) { return res.json(); })
          .then(function (meta) {
            years = meta.years || [];
            return Promise.all(
              years.map(function (year) {
                return fetch("news-data/issues-" + year + ".json").then(function (r) {
                  return r.json();
                });
              })
            );
          })
          .then(function (chunks) {
            allIssues = [].concat.apply([], chunks);
            loading = false;
            return allIssues;
          });
      }
      return Promise.all(
        years.map(function (year) {
          return fetch("news-data/issues-" + year + ".json").then(function (r) {
            return r.json();
          });
        })
      ).then(function (chunks) {
        allIssues = [].concat.apply([], chunks);
        loading = false;
        return allIssues;
      });
    }

    function renderResults(items) {
      if (!items.length) {
        results.innerHTML = '<p class="empty-state">未找到匹配结果</p>';
        return;
      }
      var html = '<ul class="search-results__list">';
      items.forEach(function (issue) {
        html +=
          '<li class="search-results__item reveal is-visible">' +
          '<a href="' +
          issue.url +
          '">' +
          '<span class="search-results__meta">' +
          issue.date +
          (issue.time ? " · " + issue.time : "") +
          " · " +
          issue.profile +
          "</span>" +
          "<strong>" +
          escapeHtml(issue.title) +
          "</strong>" +
          '<span class="search-results__excerpt">' +
          escapeHtml(issue.excerpt) +
          "</span>" +
          "</a></li>";
      });
      html += "</ul>";
      results.innerHTML = html;
    }

    function runSearch() {
      var q = (input.value || "").trim().toLowerCase();
      if (!q) {
        results.innerHTML = "";
        if (status) status.textContent = "输入关键词开始搜索";
        return;
      }
      if (status) status.textContent = "搜索中…";
      loadAllIssues()
        .then(function (issues) {
          var matched = issues.filter(function (issue) {
            return (
              (issue.title || "").toLowerCase().indexOf(q) !== -1 ||
              (issue.excerpt || "").toLowerCase().indexOf(q) !== -1
            );
          });
          if (status) {
            status.textContent = "找到 " + matched.length + " 条结果";
          }
          renderResults(matched.slice(0, 50));
        })
        .catch(function () {
          if (status) status.textContent = "加载索引失败，请刷新重试";
        });
    }

    var timer = null;
    input.addEventListener("input", function () {
      clearTimeout(timer);
      timer = setTimeout(runSearch, 220);
    });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        clearTimeout(timer);
        runSearch();
      }
    });
  }

  initLoadMore();
  initArchiveTabs();
  initSearch();
})();
