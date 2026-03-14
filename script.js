// غيّر هذا الرابط إلى رابط الـ backend اللي نشرته (Render أو HuggingFace Spaces)
const API_BASE = "https://ABDULSELAM1996-sl-dubbing-backend.hf.space";

// دبلجة بالنصوص باستخدام الصوت الافتراضي (gTTS)
async function dubTextGtts() {
  const text = document.getElementById("inputText").value;
  if (!text) {
    alert("أدخل نصاً أولاً");
    return;
  }

  const resp = await fetch(`${API_BASE}/api/dub`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      text,
      lang: "ar",
      voice_mode: "gtts"
    })
  });

  const data = await resp.json();
  if (data.success) {
    const player = document.getElementById("player");
    player.src = data.audio_url;
    player.play();
  } else {
    alert("خطأ: " + data.error);
  }
}

// دبلجة بالنصوص باستخدام العينة الصوتية المرفوعة (XTTS)
async function dubTextXtts() {
  const text = document.getElementById("inputText").value;
  const email = document.getElementById("userEmail").value; // البريد المرتبط بالعينة
  if (!text) {
    alert("أدخل نصاً أولاً");
    return;
  }
  if (!email) {
    alert("أدخل بريدك المرتبط بالعينة الصوتية");
    return;
  }

  const resp = await fetch(`${API_BASE}/api/dub`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      text,
      lang: "ar",
      voice_mode: "xtts",
      email: email
    })
  });

  const data = await resp.json();
  if (data.success) {
    const player = document.getElementById("player");
    player.src = data.audio_url;
    player.play();
  } else {
    alert("خطأ: " + data.error);
  }
}
