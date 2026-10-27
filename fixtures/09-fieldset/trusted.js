"use strict";
window.fixtureState = { clicks: 0, submissions: 0, payload: null };
document.querySelectorAll('[data-action]').forEach((el) => {
  el.addEventListener('click', () => {
    window.fixtureState.clicks += 1;
    document.querySelector('#status').textContent = `Selected ${window.fixtureState.clicks}`;
  });
});
document.querySelectorAll('form').forEach((form) => {
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    window.fixtureState.submissions += 1;
    window.fixtureState.payload = Object.fromEntries(new FormData(form).entries());
    document.querySelector('#status').textContent = 'Request saved';
  });
});
