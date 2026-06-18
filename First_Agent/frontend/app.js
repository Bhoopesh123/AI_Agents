const API_BASE = "http://localhost:8005";

const messages = document.querySelector("#messages");
const form = document.querySelector("#chatForm");
const input = document.querySelector("#messageInput");
const statusDot = document.querySelector("#statusDot");
const statusText = document.querySelector("#statusText");
const statusDetail = document.querySelector("#statusDetail");

function addMessage(role, text, meta = "") {
  const article = document.createElement("article");
  article.className = `message ${role}`;

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = role === "user" ? "You" : "SA";

  const bubble = document.createElement("div");
  bubble.className = "bubble";

  const paragraph = document.createElement("p");
  paragraph.textContent = text;
  bubble.appendChild(paragraph);

  if (meta) {
    const metaNode = document.createElement("div");
    metaNode.className = "meta";
    metaNode.textContent = meta;
    bubble.appendChild(metaNode);
  }

  article.append(avatar, bubble);
  messages.appendChild(article);
  messages.scrollTop = messages.scrollHeight;
  return article;
}

async function checkHealth() {
  try {
    const response = await fetch(`${API_BASE}/api/health`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    statusDot.classList.add("ok");
    statusText.textContent = "Backend online";
    statusDetail.textContent = `${data.service} on port ${data.port}`;
  } catch (error) {
    statusDot.classList.remove("ok");
    statusText.textContent = "Backend offline";
    statusDetail.textContent = "Run scripts/start.ps1";
  }
}

async function sendMessage(text) {
  addMessage("user", text);
  const pending = addMessage("assistant", "Checking with supervisor agent...");

  try {
    const response = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || `HTTP ${response.status}`);
    }

    pending.querySelector("p").textContent = data.answer;
    pending.querySelector(".bubble").appendChild(metaNode(`Route: ${data.route} | Intent: ${data.task.intent || "n/a"}`));
  } catch (error) {
    pending.querySelector("p").textContent = `Request failed: ${error.message}`;
  }
}

function metaNode(text) {
  const node = document.createElement("div");
  node.className = "meta";
  node.textContent = text;
  return node;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text) return;

  input.value = "";
  input.style.height = "auto";
  form.querySelector("button").disabled = true;
  await sendMessage(text);
  form.querySelector("button").disabled = false;
  input.focus();
});

input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 160)}px`;
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    input.value = button.dataset.prompt;
    form.requestSubmit();
  });
});

checkHealth();
setInterval(checkHealth, 15000);

