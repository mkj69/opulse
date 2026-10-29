/* Homepage explainer video: native controls appear on hover or keyboard focus, and with
   prefers-reduced-motion the video does not autoplay; the poster shows with a play button. */
(function () {
  "use strict";
  if (window.__opulseVideoPlayerInitialized) return;
  window.__opulseVideoPlayerInitialized = true;
  let activeRoot = null;
  let paletteObserver = null;

  function play(video, button) {
    const attempt = video.play();
    if (attempt && attempt.catch) attempt.catch(() => { if (button) button.hidden = false; });
  }

  function setup(root) {
    const video = root.querySelector("video");
    if (!video || root.dataset.ready) return;
    root.dataset.ready = "1";
    const button = root.querySelector(".op-video-play");
    const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const initialAutoplay = video.autoplay;
    video.autoplay = false;
    video.removeAttribute("autoplay");
    const webm = video.querySelector('source[type="video/webm"]');
    const mp4 = video.querySelector('source[type="video/mp4"]');
    let currentTheme = "light";
    let swapNumber = 0;
    let metadataHandler = null;
    let pendingResume = false;
    let pendingTime = 0;

    function syncTheme(initial) {
      const theme = document.body.getAttribute("data-md-color-scheme") === "slate" ? "dark" : "light";
      if (theme === currentTheme) return false;
      const currentTime = Number.isFinite(video.currentTime) ? video.currentTime : 0;
      const wasPaused = video.paused;
      const time = metadataHandler && video.readyState < 1 ? pendingTime : currentTime;
      pendingTime = time;
      const resume = !reduce && (initial ? initialAutoplay : (metadataHandler && video.readyState < 1 ? pendingResume : !wasPaused));
      pendingResume = resume;
      currentTheme = theme;
      const number = ++swapNumber;
      if (metadataHandler) video.removeEventListener("loadedmetadata", metadataHandler);
      video.pause();
      webm.src = video.dataset[theme + "Webm"];
      mp4.src = video.dataset[theme + "Mp4"];
      video.poster = video.dataset[theme + "Poster"];
      metadataHandler = () => {
        if (number !== swapNumber || video.readyState < 1) return;
        video.removeEventListener("loadedmetadata", metadataHandler);
        metadataHandler = null;
        pendingResume = false;
        if (Number.isFinite(video.duration)) {
          try { video.currentTime = Math.min(time, Math.max(0, video.duration - 0.01)); }
          catch (_) { /* The browser may not have a seekable range yet. */ }
        }
        if (resume) play(video, button);
      };
      video.load();
      video.addEventListener("loadedmetadata", metadataHandler);
      if (video.readyState >= 1) metadataHandler();
      return true;
    }

    if (paletteObserver) paletteObserver.disconnect();
    const observer = new MutationObserver(() => {
      if (root.isConnected) syncTheme(false);
      else observer.disconnect();
    });
    paletteObserver = observer;
    paletteObserver.observe(document.body, { attributes: true, attributeFilter: ["data-md-color-scheme"] });
    activeRoot = root;
    const show = () => { video.controls = true; };
    const hide = () => {
      if (!root.contains(document.activeElement) && !root.matches(":hover")) video.controls = false;
    };
    root.addEventListener("mouseenter", show);
    root.addEventListener("mouseleave", hide);
    root.addEventListener("focusin", show);
    root.addEventListener("focusout", () => setTimeout(hide, 0));

    if (reduce) {
      video.autoplay = false;
      video.removeAttribute("autoplay");
      video.pause();
      if (button) {
        button.hidden = false;
        button.addEventListener("click", () => {
          button.hidden = true;
          video.controls = true;
          play(video, button);
          video.focus();
        });
        video.addEventListener("play", () => { button.hidden = true; });
      }
    }
    const swapped = syncTheme(true);
    if (!reduce && !swapped && video.paused) {
      // Autoplay can be skipped after instant navigation; muted playback is always allowed.
      play(video, button);
    }
  }

  const run = () => {
    const root = document.querySelector(".op-video");
    if (activeRoot && activeRoot !== root && paletteObserver) {
      paletteObserver.disconnect();
      paletteObserver = null;
      activeRoot = null;
    }
    if (root) setup(root);
  };
  if (window.document$ && typeof window.document$.subscribe === "function") window.document$.subscribe(run);
  else if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run);
  else run();
})();
