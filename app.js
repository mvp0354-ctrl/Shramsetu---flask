const storageKey = "shramsetu-data";

const defaultData = {
  users: [
    { role: "contractor", username: "contractor1", password: "1234", name: "Rakesh Buildcon" },
    { role: "labour", username: "labour1", password: "1234", name: "Suresh Kumar" },
    { role: "client", username: "client1", password: "1234", name: "Metro Infra Client" },
    { role: "admin", username: "admin1", password: "1234", name: "Portal Admin" }
  ],
  labourers: [
    {
      id: 1,
      name: "Suresh Kumar",
      skill: "Mason",
      phone: "9876543210",
      location: "Nagpur Site A",
      wage: 750,
      status: "Assigned",
      contractor: "Rakesh Buildcon",
      labourUsername: "labour1"
    },
    {
      id: 2,
      name: "Anita Devi",
      skill: "Electrician",
      phone: "9123456780",
      location: "Pune Tower Project",
      wage: 900,
      status: "Assigned",
      contractor: "Rakesh Buildcon",
      labourUsername: ""
    }
  ]
};

const state = {
  currentUser: null,
  data: loadData()
};

const loginForm = document.getElementById("loginForm");
const roleInput = document.getElementById("role");
const usernameInput = document.getElementById("username");
const passwordInput = document.getElementById("password");
const dashboardSection = document.getElementById("dashboardSection");
const dashboardTitle = document.getElementById("dashboardTitle");
const dashboardNote = document.getElementById("dashboardNote");
const dashboardContent = document.getElementById("dashboardContent");
const demoCredentials = document.getElementById("demoCredentials");
const logoutBtn = document.getElementById("logoutBtn");
const heroStats = document.getElementById("heroStats");

renderHeroStats();
renderDemoCredentials();

loginForm.addEventListener("submit", handleLogin);
logoutBtn.addEventListener("click", handleLogout);

function loadData() {
  const saved = localStorage.getItem(storageKey);
  return saved ? JSON.parse(saved) : structuredClone(defaultData);
}

function saveData() {
  localStorage.setItem(storageKey, JSON.stringify(state.data));
}

function handleLogin(event) {
  event.preventDefault();

  const role = roleInput.value;
  const username = usernameInput.value.trim();
  const password = passwordInput.value.trim();

  const match = state.data.users.find((user) => (
    user.role === role &&
    user.username === username &&
    user.password === password
  ));

  if (!match) {
    alert("Invalid login. Please use one of the demo accounts.");
    return;
  }

  state.currentUser = match;
  loginForm.reset();
  renderDashboard();
}

function handleLogout() {
  state.currentUser = null;
  dashboardSection.classList.add("hidden");
  dashboardContent.innerHTML = "";
}

function renderDashboard() {
  if (!state.currentUser) {
    return;
  }

  dashboardSection.classList.remove("hidden");
  dashboardTitle.textContent = `${capitalize(state.currentUser.role)} Dashboard`;
  dashboardNote.textContent = getDashboardNote(state.currentUser);
  dashboardContent.innerHTML = "";

  if (state.currentUser.role === "contractor") {
    renderTemplate("contractorTemplate");
    renderContractorDashboard();
  }

  if (state.currentUser.role === "labour") {
    renderTemplate("labourTemplate");
    renderLabourDashboard();
  }

  if (state.currentUser.role === "client") {
    renderTemplate("clientTemplate");
    renderClientDashboard();
  }

  if (state.currentUser.role === "admin") {
    renderTemplate("adminTemplate");
    renderAdminDashboard();
  }

  renderHeroStats();
}

function renderTemplate(templateId) {
  const template = document.getElementById(templateId);
  dashboardContent.appendChild(template.content.cloneNode(true));
}

function renderContractorDashboard() {
  const labourForm = document.getElementById("labourForm");
  const contractorLabourList = document.getElementById("contractorLabourList");
  const contractorName = state.currentUser.name;
  const ownLabourers = state.data.labourers.filter((labour) => labour.contractor === contractorName);

  labourForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const formData = new FormData(labourForm);
    const name = formData.get("name").trim();
    const skill = formData.get("skill").trim();
    const phone = formData.get("phone").trim();
    const location = formData.get("location").trim();
    const wage = Number(formData.get("wage"));
    const status = formData.get("status");

    const nextId = state.data.labourers.reduce((max, item) => Math.max(max, item.id), 0) + 1;
    const labourUsername = slugify(name) + nextId;

    state.data.labourers.push({
      id: nextId,
      name,
      skill,
      phone,
      location,
      wage,
      status,
      contractor: contractorName,
      labourUsername
    });

    state.data.users.push({
      role: "labour",
      username: labourUsername,
      password: "1234",
      name
    });

    saveData();
    labourForm.reset();
    renderDashboard();
    alert(`Labour added. Login created: ${labourUsername} / 1234`);
  });

  contractorLabourList.innerHTML = renderTable(
    ["Name", "Skill", "Phone", "Location", "Wage/Day", "Status", "Login"],
    ownLabourers.map((labour) => [
      labour.name,
      labour.skill,
      labour.phone,
      labour.location,
      `Rs. ${labour.wage}`,
      `<span class="status-badge">${labour.status}</span>`,
      labour.labourUsername || "-"
    ]),
    "No labour records added yet."
  );
}

function renderLabourDashboard() {
  const labourProfile = document.getElementById("labourProfile");
  const labourRecord = state.data.labourers.find((labour) => labour.labourUsername === state.currentUser.username);

  if (!labourRecord) {
    labourProfile.innerHTML = `<div class="empty-state">No work record is assigned to this labour account yet.</div>`;
    return;
  }

  labourProfile.innerHTML = `
    <div class="profile-card">
      ${profileRow("Name", labourRecord.name)}
      ${profileRow("Skill", labourRecord.skill)}
      ${profileRow("Location", labourRecord.location)}
      ${profileRow("Contractor", labourRecord.contractor)}
      ${profileRow("Daily Wage", `Rs. ${labourRecord.wage}`)}
      ${profileRow("Status", `<span class="status-badge">${labourRecord.status}</span>`)}
      ${profileRow("Phone", labourRecord.phone)}
    </div>
  `;
}

function renderClientDashboard() {
  const clientOverview = document.getElementById("clientOverview");
  const grouped = groupByLocation(state.data.labourers);

  clientOverview.innerHTML = renderTable(
    ["Location", "Workers", "Skills", "Average Wage", "Contractors"],
    Object.entries(grouped).map(([location, labourers]) => {
      const skills = [...new Set(labourers.map((labour) => labour.skill))].join(", ");
      const contractors = [...new Set(labourers.map((labour) => labour.contractor))].join(", ");
      const average = Math.round(labourers.reduce((sum, labour) => sum + labour.wage, 0) / labourers.length);
      return [location, labourers.length, skills, `Rs. ${average}`, contractors];
    }),
    "No project locations available right now."
  );
}

function renderAdminDashboard() {
  const adminSummary = document.getElementById("adminSummary");
  const adminRecords = document.getElementById("adminRecords");
  const labourers = state.data.labourers;
  const contractors = new Set(labourers.map((labour) => labour.contractor)).size;
  const locations = new Set(labourers.map((labour) => labour.location)).size;
  const totalWages = labourers.reduce((sum, labour) => sum + labour.wage, 0);
  const activeWorkers = labourers.filter((labour) => labour.status === "Assigned").length;

  adminSummary.innerHTML = [
    metricCard("Total Labourers", labourers.length),
    metricCard("Contractors", contractors),
    metricCard("Locations", locations),
    metricCard("Daily Wage Sum", `Rs. ${totalWages}`),
    metricCard("Assigned Workers", activeWorkers),
    metricCard("Portal Users", state.data.users.length)
  ].join("");

  adminRecords.innerHTML = renderTable(
    ["Name", "Contractor", "Location", "Skill", "Wage/Day", "Status"],
    labourers.map((labour) => [
      labour.name,
      labour.contractor,
      labour.location,
      labour.skill,
      `Rs. ${labour.wage}`,
      `<span class="status-badge">${labour.status}</span>`
    ]),
    "No labour records found."
  );
}

function renderDemoCredentials() {
  demoCredentials.innerHTML = state.data.users
    .filter((user) => user.role !== "labour" || user.username === "labour1")
    .map((user) => `
      <div class="credential">
        <strong>${capitalize(user.role)}</strong>
        <span>${user.username} / ${user.password}</span>
      </div>
    `)
    .join("");
}

function renderHeroStats() {
  const labourers = state.data.labourers;
  const locations = new Set(labourers.map((labour) => labour.location)).size;
  const contractors = new Set(labourers.map((labour) => labour.contractor)).size;
  const wages = labourers.reduce((sum, labour) => sum + labour.wage, 0);

  heroStats.innerHTML = [
    metricCard("Labours", labourers.length),
    metricCard("Locations", locations),
    metricCard("Contractors", contractors),
    metricCard("Declared Wages", `Rs. ${wages}`)
  ].join("");
}

function getDashboardNote(user) {
  const notes = {
    labour: `Welcome ${user.name}. Here you can check your work location, contractor, and daily wage.`,
    contractor: `Welcome ${user.name}. Register labourers, create their login, and declare site wages here.`,
    client: `Welcome ${user.name}. Track labour distribution and wage visibility across project locations.`,
    admin: `Welcome ${user.name}. Review all workers, contractors, locations, and wage declarations.`
  };

  return notes[user.role];
}

function renderTable(headers, rows, emptyText) {
  if (!rows.length) {
    return `<div class="empty-state">${emptyText}</div>`;
  }

  return `
    <table>
      <thead>
        <tr>${headers.map((header) => `<th>${header}</th>`).join("")}</tr>
      </thead>
      <tbody>
        ${rows.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join("")}
      </tbody>
    </table>
  `;
}

function groupByLocation(labourers) {
  return labourers.reduce((groups, labour) => {
    groups[labour.location] = groups[labour.location] || [];
    groups[labour.location].push(labour);
    return groups;
  }, {});
}

function metricCard(label, value) {
  return `<div class="metric"><span>${label}</span><strong>${value}</strong></div>`;
}

function profileRow(label, value) {
  return `<div class="profile-row"><strong>${label}</strong><span>${value}</span></div>`;
}

function capitalize(value) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function slugify(value) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "");
}
