'use strict';

const PORTAL = 'https://zonaprivada.edistribucion.com/';
const NEEDED = ['sid', 'oid', 'sid_Client', 'inst', 'clientSrc'];

(async () => {
  const message = document.getElementById('message');
  try {
    const cookies = await chrome.cookies.getAll({ url: PORTAL });
    const wanted = {};
    for (const cookie of cookies) {
      if (NEEDED.includes(cookie.name)) wanted[cookie.name] = cookie.value;
    }
    if (!wanted.sid) {
      message.textContent = 'No sid cookie found. Log in to the portal first.';
      return;
    }
    const payload = btoa(unescape(encodeURIComponent(JSON.stringify({ cookies: wanted }))));
    const url = 'edist://session?data=' + encodeURIComponent(payload);
    message.textContent = 'Sending session...';
    const link = document.createElement('a');
    link.href = url;
    document.body.appendChild(link);
    link.click();
    link.remove();
    message.textContent = 'Session sent. You can close this popup.';
  } catch (error) {
    message.textContent = 'Error: ' + error;
  }
})();
