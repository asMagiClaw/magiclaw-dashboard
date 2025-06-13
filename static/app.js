const socket = io();
const logOutput = document.getElementById("logOutput");
const runBtn = document.getElementById("runBtn");
const stopBtn = document.getElementById("stopBtn");
const AUTH_TOKEN = "magiclaw";

// Append log message to the output area
function appendLog(message) {
  const line = document.createElement("div");
  line.classList.add("whitespace-pre", "font-mono", "text-sm", "py-0.5");

  if (message.includes(" - INFO - ")) {
    line.classList.add("text-green-500");
  } else if (message.includes(" - WARNING - ")) {
    line.classList.add("text-yellow-400");
  } else if (message.includes(" - ERROR - ")) {
    line.classList.add("text-red-600", "font-bold");
  } else {
    line.classList.add("text-white");
  }

  line.textContent = message;
  logOutput.appendChild(line);
  logOutput.scrollTop = logOutput.scrollHeight;
}

// Format fixed-point array for display
function formatFixedArray(arr) {
  return arr.map(v => `<span class="fixed-num">${v.toFixed(2)}</span>`).join(",");
}

// Update the status display with data from the server
socket.on("status_update", (data) => {
  document.getElementById("motor-angle").textContent = data.motor_angle.toFixed(2);
  document.getElementById("motor-speed").textContent = data.motor_speed.toFixed(2);
  document.getElementById("motor-iq").textContent = data.motor_iq.toFixed(2);
  document.getElementById("motor-temp").textContent = data.motor_temp.toFixed(1);
  document.getElementById("claw-angle").textContent = data.claw_angle.toFixed(2);

  document.getElementById("finger0-pose").innerHTML = formatFixedArray(data.finger_0_pose);
  document.getElementById("finger0-force").innerHTML = formatFixedArray(data.finger_0_force);
  document.getElementById("finger1-pose").innerHTML = formatFixedArray(data.finger_1_pose);
  document.getElementById("finger1-force").innerHTML = formatFixedArray(data.finger_1_force);

  // Update images with cache-busting query parameter
  const finger0Img = document.getElementById("finger0-img");
  const finger1Img = document.getElementById("finger1-img");

  if (finger0Img && data.finger_0_img) {
    finger0Img.src = `${data.finger_0_img}#${new Date().getTime()}`;
  }

  if (finger1Img && data.finger_1_img) {
    finger1Img.src = `${data.finger_1_img}#${new Date().getTime()}`;
  }

  document.getElementById("magiclaw-pose").innerHTML = formatFixedArray(data.magiclaw_pose);
});

socket.on("log", appendLog);

// Control buttons for starting and stopping the MagicLaw process
runBtn.addEventListener("click", async () => {
  const res = await fetch("/exec", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${AUTH_TOKEN}`
    },
    body: JSON.stringify({ cmd: "run-magiclaw" }),
  });
  const json = await res.json();
  appendLog(`[client] Run: ${JSON.stringify(json)}`);
});

stopBtn.addEventListener("click", async () => {
  const res = await fetch("/exec", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${AUTH_TOKEN}`
    },
    body: JSON.stringify({ cmd: "stop-magiclaw" }),
  });
  const json = await res.json();
  appendLog(`[client] Stop: ${JSON.stringify(json)}`);
});
