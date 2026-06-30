/** 文章页阅读进度条 */
(function () {
  var bar = document.getElementById("reading-progress");
  if (!bar) return;

  function update() {
    var doc = document.documentElement;
    var scrollTop = doc.scrollTop || document.body.scrollTop;
    var height = doc.scrollHeight - doc.clientHeight;
    var progress = height > 0 ? (scrollTop / height) * 100 : 0;
    bar.style.width = progress + "%";
  }

  window.addEventListener("scroll", update, { passive: true });
  update();
})();
