const msgBox = document.getElementById("messages");
const input = document.getElementById("input");
const send = document.getElementById("send");

// ✅ FIX: always render past chats into the real list container
const pastBox = document.querySelector(".past-list");

const newChatBtn = document.getElementById("newChatBtn");
const chatTitle = document.querySelector(".chat-title");

/* ============================= */
/* STATE */
/* ============================= */
let chats = JSON.parse(localStorage.getItem("sami_chats")) || [];
let activeChatId = localStorage.getItem("active_chat_id");

/* ============================= */
/* HELPERS */
/* ============================= */
function saveState() {
  localStorage.setItem("sami_chats", JSON.stringify(chats));
  localStorage.setItem("active_chat_id", activeChatId);
}

function getActiveChat() {
  return chats.find(c => c.id === activeChatId);
}

function scrollToBottom() {
  requestAnimationFrame(() => {
    msgBox.scrollTop = msgBox.scrollHeight;
  });
}

function addBubble(role, text) {
  const div = document.createElement("div");
  div.className = `bubble ${role}`;
  div.textContent = text;
  msgBox.appendChild(div);
  scrollToBottom();
  return div;
}

/* ============================= */
/* PAST CHATS (DISPLAY ONLY) */
/* ============================= */
function renderPastChats() {
  if (!pastBox) return;
  pastBox.innerHTML = "";

  // newest first
  let sorted = [...chats].sort(
    (a, b) => Number(b.createdAt) - Number(a.createdAt)
  );

  // ✅ active chat always first
  const active = getActiveChat();
  if (active) {
    sorted = [active, ...sorted.filter(c => c.id !== active.id)];
  }

  // only show 5
  const latestChats = sorted.slice(0, 5);

  latestChats.forEach(chat => {
    const btn = document.createElement("button");
    btn.textContent = chat.title || "New Chat";

    // visible but not clickable
    btn.className = "past-chat-item";
    btn.tabIndex = -1;

    // ✅ highlight active
    if (chat.id === activeChatId) {
      btn.style.border = "2px solid #00b37e";
      btn.style.opacity = "1";
      btn.style.fontWeight = "700";
    }

    pastBox.appendChild(btn);
  });
}

/* ============================= */
/* RENDER MESSAGES */
/* ============================= */
function renderMessages() {
  msgBox.innerHTML = "";
  const chat = getActiveChat();
  if (!chat) return;

  chatTitle.textContent = chat.title;

  chat.messages.forEach(m => {
    addBubble(m.role, m.text);
  });
}

/* ============================= */
/* NEW CHAT */
/* ============================= */
function createNewChat(force = false) {
  const active = getActiveChat();

  // ✅ If active is already empty New Chat and not forced, reuse
  if (
    !force &&
    active &&
    active.title === "New Chat" &&
    active.messages &&
    active.messages.length === 0
  ) {
    renderPastChats();
    renderMessages();
    return;
  }

  // ✅ prevent multiple empty New Chat globally
  const existingEmptyNew = chats.find(
    c => c.title === "New Chat" && c.messages && c.messages.length === 0
  );

  if (!force && existingEmptyNew) {
    activeChatId = existingEmptyNew.id;
    saveState();
    renderPastChats();
    renderMessages();
    return;
  }

  const id = Date.now().toString();

  chats.push({
    id,
    title: "New Chat",
    messages: [],
    createdAt: Date.now()
  });

  activeChatId = id;
  saveState();
  renderPastChats();
  renderMessages();
}

if (newChatBtn) {
  newChatBtn.onclick = () => createNewChat(false); // force new chat when clicked
}

/* ============================= */
/* FEEDBACK */
/* ============================= */
function addFeedbackUI({ chatId, question, answer }) {
  const wrapper = document.createElement("div");
  wrapper.className = "feedback";

  const up = document.createElement("button");
  up.textContent = "👍";

  const down = document.createElement("button");
  down.textContent = "👎";

  const comment = document.createElement("button");
  comment.textContent = "💬";

  const thankYou = document.createElement("span");
  thankYou.className = "feedback-thankyou";
  thankYou.textContent = "Thanks for your feedback";

  function sendFeedback(payload) {
    fetch("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
  }

  function finalize() {
    wrapper.innerHTML = "";
    wrapper.appendChild(thankYou);
  }

  up.onclick = () => {
    sendFeedback({ chatId, question, answer, rating: "up" });
    finalize();
  };

  down.onclick = () => {
    sendFeedback({ chatId, question, answer, rating: "down" });
    finalize();
  };

  comment.onclick = () => {
    const box = document.createElement("div");
    box.className = "feedback-comment-box";

    const textarea = document.createElement("textarea");
    textarea.placeholder = "Add a comment…";

    const sendBtn = document.createElement("button");
    sendBtn.textContent = "Send";

    sendBtn.onclick = () => {
      sendFeedback({
        chatId,
        question,
        answer,
        rating: "comment",
        comment: textarea.value
      });
      box.remove();
      finalize();
    };

    box.append(textarea, sendBtn);
    msgBox.appendChild(box);
    textarea.focus();
    scrollToBottom();
  };

  wrapper.append(up, down, comment);
  msgBox.appendChild(wrapper);
  scrollToBottom();
}

/* ============================= */
/* SEND PROMPT */
/* ============================= */
async function sendPrompt(text) {
  if (!text.trim()) return;

  const chat = getActiveChat();
  if (!chat) return;

  // set chat title when first question asked
  if (!chat.messages.length) {
    chat.title = text.split(" ").slice(0, 5).join(" ");
  }

  chat.messages.push({ role: "user-msg", text });
  input.value = "";
  renderMessages();
  renderPastChats();
  saveState();

  send.disabled = true;
  input.disabled = true;

  const typing = addBubble("bot-msg typing", "Processing your request…");

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt: text,
        chatId: chat.id,
        chatTitle: chat.title
      })
    });

    const data = await res.json();
    typing.remove();

    const reply = data.bot_reply || "No response available.";
    chat.messages.push({ role: "bot-msg", text: reply });

    renderMessages();
    addFeedbackUI({ chatId: chat.id, question: text, answer: reply });
  } catch {
    typing.remove();
    chat.messages.push({
      role: "bot-msg",
      text: "An error occurred. Please try again."
    });
    renderMessages();
  } finally {
    send.disabled = false;
    input.disabled = false;
    saveState();
  }
}

/* ============================= */
/* EVENTS */
/* ============================= */
send.onclick = () => sendPrompt(input.value);

input.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendPrompt(input.value);
  }
});

/* ============================= */
/* INIT */
/* ============================= */
/*
✅ Required Logic:
1) If active chat is empty "New Chat" -> keep it
2) If active chat is NOT empty -> create a new chat
3) Never create duplicate empty new chats
4) New chat must always be visible in Past Chats
*/
function initChatSession() {
  // if no chats exist, create first chat
  if (!chats.length) {
    createNewChat(true);
    return;
  }

  // if activeChatId missing -> set to latest
  if (!activeChatId) {
    activeChatId = chats.sort((a, b) => Number(b.createdAt) - Number(a.createdAt))[0].id;
    saveState();
  }

  const active = getActiveChat();

  const isActiveEmptyNewChat =
    active &&
    active.title === "New Chat" &&
    active.messages &&
    active.messages.length === 0;

  if (isActiveEmptyNewChat) {
    // ✅ Keep existing empty New Chat
    return;
  }

  // ✅ Otherwise create new chat
  createNewChat(false);
}

initChatSession();
renderPastChats();
renderMessages();
