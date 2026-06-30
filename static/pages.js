/** AI Daily 页面交互：阅读进度 + 滚动显现 + 栏目导航高亮 */
(function () {
  var bar = document.getElementById("reading-progress");
  if (bar) {
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
        { threshold: 0.12, rootMargin: "0px 0px -8% 0px" }
      );

      revealItems.forEach(function (el) {
        observer.observe(el);
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
})();
