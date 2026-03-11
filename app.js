const storageKeys = {
    serverUrl: "rsk-server-url",
    adminToken: "rsk-admin-token"
};

const pages = {
    login: document.getElementById("page-login"),
    menu: document.getElementById("page-menu"),
    teamCreate: document.getElementById("page-team-create"),
    notify: document.getElementById("page-notify")
};

const statusLabel = document.getElementById("status");
const serverUrlInput = document.getElementById("serverUrl");
const adminUsernameInput = document.getElementById("adminUsername");
const adminPasswordInput = document.getElementById("adminPassword");
const adminLoginForm = document.getElementById("admin-login-form");

const goTeamCreateButton = document.getElementById("go-team-create");
const goNotifyButton = document.getElementById("go-notify");
const logoutButton = document.getElementById("logout");

const teamCreateForm = document.getElementById("team-create-form");
const newTeamCodeInput = document.getElementById("newTeamCode");
const newTeamDisplayInput = document.getElementById("newTeamDisplay");
const newTeamPasswordInput = document.getElementById("newTeamPassword");
const backFromTeamButton = document.getElementById("back-from-team");

const notifyForm = document.getElementById("notify-form");
const teamCodeSelect = document.getElementById("teamCode");
const titleInput = document.getElementById("title");
const messageInput = document.getElementById("message");
const backFromNotifyButton = document.getElementById("back-from-notify");

serverUrlInput.value = localStorage.getItem(storageKeys.serverUrl) || "https://competition.novadevlegrand.fr";

adminLoginForm.addEventListener("submit", onAdminLogin);
goTeamCreateButton.addEventListener("click", () => showPage("teamCreate"));
goNotifyButton.addEventListener("click", async () => {
    await loadTeams();
    showPage("notify");
});
logoutButton.addEventListener("click", logout);
teamCreateForm.addEventListener("submit", onCreateTeam);
backFromTeamButton.addEventListener("click", () => showPage("menu"));
notifyForm.addEventListener("submit", onSendNotification);
backFromNotifyButton.addEventListener("click", () => showPage("menu"));

showPage("login");
setStatus("Connecte-toi en admin.");

async function onAdminLogin(event) {
    event.preventDefault();

    const config = getConfig();
    if (!config) {
        return;
    }

    setStatus("Connexion admin en cours...");

    const response = await fetch(`${config.baseUrl}/api/admin/login`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            username: adminUsernameInput.value.trim(),
            password: adminPasswordInput.value
        })
    });

    if (!response.ok) {
        setStatus("Echec login admin.");
        return;
    }

    const payload = await response.json();
    localStorage.setItem(storageKeys.adminToken, payload.token);
    adminPasswordInput.value = "";
    showPage("menu");
    setStatus("Login admin valide.");
}

async function onCreateTeam(event) {
    event.preventDefault();

    const context = getAdminContext();
    if (!context) {
        return;
    }

    setStatus("Creation equipe en cours...");

    const response = await fetch(`${context.baseUrl}/api/admin/teams`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${context.token}`
        },
        body: JSON.stringify({
            code: newTeamCodeInput.value.trim().toLowerCase(),
            displayName: newTeamDisplayInput.value.trim(),
            password: newTeamPasswordInput.value
        })
    });

    if (!response.ok) {
        const details = await safeError(response);
        setStatus(`Echec creation equipe: ${details}`);
        return;
    }

    newTeamCodeInput.value = "";
    newTeamDisplayInput.value = "";
    newTeamPasswordInput.value = "";
    setStatus("Equipe creee.");
}

async function onSendNotification(event) {
    event.preventDefault();

    const context = getAdminContext();
    if (!context) {
        return;
    }

    setStatus("Envoi notification en cours...");

    const response = await fetch(`${context.baseUrl}/api/notifications`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${context.token}`
        },
        body: JSON.stringify({
            teamCode: teamCodeSelect.value,
            title: titleInput.value.trim(),
            message: messageInput.value.trim()
        })
    });

    if (!response.ok) {
        const details = await safeError(response);
        setStatus(`Echec envoi: ${details}`);
        return;
    }

    const notification = await response.json();
    const sentAt = notification.sentAtUtc || new Date().toISOString();
    setStatus(`Notification envoyee a ${notification.teamCode} a ${new Date(sentAt).toLocaleString()}.`);
    messageInput.value = "";
}

async function loadTeams() {
    const config = getConfig();
    if (!config) {
        return;
    }

    setStatus("Chargement des equipes...");

    const response = await fetch(`${config.baseUrl}/api/teams`);
    if (!response.ok) {
        setStatus("Impossible de charger les equipes.");
        return;
    }

    const teams = await response.json();
    teamCodeSelect.innerHTML = "";

    for (const team of teams) {
        const option = document.createElement("option");
        option.value = team.code;
        option.textContent = `${team.displayName} (${team.code})`;
        teamCodeSelect.appendChild(option);
    }

    setStatus(`${teams.length} equipe(s) disponible(s).`);
}

function showPage(pageName) {
    for (const key of Object.keys(pages)) {
        pages[key].classList.toggle("hidden", key !== pageName);
    }
}

function logout() {
    localStorage.removeItem(storageKeys.adminToken);
    showPage("login");
    setStatus("Deconnecte.");
}

function getConfig() {
    const baseUrl = serverUrlInput.value.trim().replace(/\/$/, "");

    if (!baseUrl) {
        setStatus("Renseigne l'URL serveur.");
        return null;
    }

    localStorage.setItem(storageKeys.serverUrl, baseUrl);
    return { baseUrl };
}

function getAdminContext() {
    const config = getConfig();
    if (!config) {
        return null;
    }

    const token = localStorage.getItem(storageKeys.adminToken);
    if (!token) {
        setStatus("Session admin absente. Reconnecte-toi.");
        showPage("login");
        return null;
    }

    return { ...config, token };
}

async function safeError(response) {
    try {
        const payload = await response.json();
        return payload.error || `HTTP ${response.status}`;
    } catch {
        return `HTTP ${response.status}`;
    }
}

function setStatus(message) {
    statusLabel.textContent = message;
}
