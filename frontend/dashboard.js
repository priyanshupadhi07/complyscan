// Detect if running locally on a dev server (e.g. port 3000 or 5500) or directly on Vercel
const isLocalStaticDev = (window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost") 
                         && window.location.port !== "8000";

const API_BASE = isLocalStaticDev ? "http://127.0.0.1:8000" : "";
const API_BASE_URL = API_BASE;

let violationsChart = null;
let complianceChart = null;


// ================================
// ELEMENTS
// ================================

const totalScansElement =
    document.getElementById("totalScans");

const compliantScansElement =
    document.getElementById("compliantScans");

const nonCompliantScansElement =
    document.getElementById("nonCompliantScans");

const scanList =
    document.getElementById("scanList");

const dashboardError =
    document.getElementById("dashboardError");

const refreshButton =
    document.getElementById("refreshButton");


// ================================
// SHOW ERROR
// ================================

function showError(message) {
    if (dashboardError) {
        dashboardError.textContent = message;
        dashboardError.style.display = "block";
    }
}


// ================================
// HIDE ERROR
// ================================

function hideError() {
    if (dashboardError) {
        dashboardError.style.display = "none";
    }
}


// ================================
// FETCH DASHBOARD DATA (FIXED URL)
// ================================

async function loadDashboard() {

    hideError();

    try {
        // Correct endpoint: /api/dashboard
        const response = await fetch(`${API_BASE}/api/dashboard`);

        if (!response.ok) {
            throw new Error(`Dashboard API returned status ${response.status}`);
        }

        const data = await response.json();

        updateStats(data);

        updateViolationChart(
            data.violation_breakdown || {}
        );

        updateComplianceChart(
            data.compliant || 0,
            data.non_compliant || 0
        );

    } catch (error) {

        console.error("Dashboard load error:", error);

        showError(
            "Dashboard data could not be loaded. Make sure the backend is running."
        );

        updateStats({
            total_scans: 0,
            compliant: 0,
            non_compliant: 0
        });

        updateViolationChart({});

        updateComplianceChart(0, 0);
    }
}


// ================================
// UPDATE STAT CARDS
// ================================

function updateStats(data) {
    if (totalScansElement) {
        totalScansElement.textContent = data.total_scans ?? 0;
    }
    if (compliantScansElement) {
        compliantScansElement.textContent = data.compliant ?? 0;
    }
    if (nonCompliantScansElement) {
        nonCompliantScansElement.textContent = data.non_compliant ?? 0;
    }
}


// ================================
// VIOLATION BAR CHART
// ================================

function updateViolationChart(violations) {

    const canvas =
        document.getElementById("violationsChart");

    if (!canvas) return;

    if (violationsChart) {
        violationsChart.destroy();
    }

    const labels = Object.keys(violations);
    const values = Object.values(violations);

    violationsChart = new Chart(canvas, {

        type: "bar",

        data: {
            labels: labels.length
                ? labels
                : ["No violations yet"],

            datasets: [
                {
                    label: "Violations",
                    data: values.length
                        ? values
                        : [0],
                    backgroundColor: "#ef6c35",
                    borderWidth: 0,
                    borderRadius: 8
                }
            ]
        },

        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        precision: 0
                    }
                },
                x: {
                    grid: {
                        display: false
                    }
                }
            }
        }
    });
}


// ================================
// COMPLIANCE PIE CHART
// ================================

function updateComplianceChart(
    compliant,
    nonCompliant
) {

    const canvas =
        document.getElementById("complianceChart");

    if (!canvas) return;

    if (complianceChart) {
        complianceChart.destroy();
    }

    const hasData = (compliant + nonCompliant) > 0;

    complianceChart = new Chart(canvas, {

        type: "doughnut",

        data: {
            labels: hasData 
                ? ["Compliant", "Non-Compliant"]
                : ["No Scans"],

            datasets: [
                {
                    data: hasData 
                        ? [compliant, nonCompliant] 
                        : [1],
                    backgroundColor: hasData
                        ? ["#168b78", "#d94b3d"]
                        : ["#dfe5df"],
                    borderWidth: 0
                }
            ]
        },

        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: "68%",
            plugins: {
                legend: {
                    position: "bottom"
                }
            }
        }
    });
}


// ================================
// FETCH PAST SCANS
// ================================

async function loadScans() {

    if (!scanList) return;

    try {
        const response = await fetch(`${API_BASE}/api/scans`);

        if (!response.ok) {
            throw new Error(`Scans API returned status ${response.status}`);
        }

        const data = await response.json();
        renderScans(data);

    } catch (error) {

        console.error("Scans load error:", error);

        scanList.innerHTML = `
            <div class="empty-state">
                <strong>No scan history available</strong>
                <span>
                    Scan history will appear here once scans are completed.
                </span>
            </div>
        `;
    }
}


// ================================
// RENDER SCANS WITH RENAME & REMOVE
// ================================

function renderScans(data) {
    if (!scanList) return;

    let scans = data;
    if (data && Array.isArray(data.scans)) {
        scans = data.scans;
    }

    if (!Array.isArray(scans) || scans.length === 0) {
        scanList.innerHTML = `
            <div class="empty-state">
                <strong>No scans yet</strong>
                <span>Your previous compliance scans will appear here.</span>
            </div>
        `;
        return;
    }

    scanList.innerHTML = "";

    // Read any locally saved custom names
    const customNames = JSON.parse(localStorage.getItem("complyscan_custom_names") || "{}");

    scans.slice(0, 15).forEach(scan => {
        const scanId = scan.id ?? scan.scan_id ?? "";
        
        // Priority: Local Storage Custom Name -> Backend Title -> Default Fallback
        const defaultTitle = `Label Scan #${scanId || "—"}`;
        const scanTitle = customNames[scanId] || scan.title || scan.product_name || defaultTitle;

        const rawStatus = String(scan.overall_status ?? scan.status ?? "").toLowerCase();
        const isCompliant = rawStatus === "pass" || 
            (rawStatus.includes("compliant") && !rawStatus.includes("non"));

        const dateValue = scan.created_at ?? scan.scan_time ?? scan.timestamp ?? "";
        const formattedDate = formatDate(dateValue);

        const statusClass = isCompliant ? "pass" : "fail";
        const displayStatus = isCompliant ? "Compliant" : "Non-Compliant";

        const wrapper = document.createElement("div");
        wrapper.className = "scan-item-wrapper";
        wrapper.id = `scan-row-${scanId}`;

        wrapper.innerHTML = `
            <a href="report.html?id=${encodeURIComponent(scanId)}" class="scan-clickable">
                <div class="scan-info">
                    <div class="scan-title" id="title-${scanId}">
                        ${escapeHTML(String(scanTitle))}
                    </div>
                    <div class="scan-date">
                        ${escapeHTML(formattedDate)}
                    </div>
                </div>
                <span class="status-badge ${statusClass}">
                    ${displayStatus}
                </span>
            </a>
            <div class="scan-actions">
                <button type="button" class="btn-icon rename" onclick="renameScanItem('${scanId}')" title="Rename scan">
                    ✏️ Rename
                </button>
                <button type="button" class="btn-icon delete" onclick="deleteScanItem('${scanId}')" title="Delete scan">
                    🗑️ Remove
                </button>
            </div>
        `;

        scanList.appendChild(wrapper);
    });
}

// ================================
// ACTION HANDLERS: RENAME & DELETE
// ================================

window.renameScanItem = async function(scanId) {
    const titleElement = document.getElementById(`title-${scanId}`);
    const currentTitle = titleElement ? titleElement.textContent.trim() : "";
    
    const newTitle = prompt("Enter a new name for this scan:", currentTitle);
    if (!newTitle || newTitle.trim() === "" || newTitle === currentTitle) {
        return;
    }

    const trimmedTitle = newTitle.trim();

    // 1. Save immediately in localStorage for instant UI feedback
    const customNames = JSON.parse(localStorage.getItem("complyscan_custom_names") || "{}");
    customNames[scanId] = trimmedTitle;
    localStorage.setItem("complyscan_custom_names", JSON.stringify(customNames));

    if (titleElement) {
        titleElement.textContent = trimmedTitle;
    }

    // 2. Persist to backend
    try {
        await fetch(`${API_BASE}/api/scans/${scanId}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title: trimmedTitle })
        });
    } catch (e) {
        console.warn("Backend rename skipped/failed:", e);
    }
};

window.deleteScanItem = async function(scanId) {
    const confirmDelete = confirm(`Are you sure you want to delete Scan #${scanId}?`);
    if (!confirmDelete) return;

    // 1. Remove from UI immediately
    const row = document.getElementById(`scan-row-${scanId}`);
    if (row) {
        row.remove();
    }

    // 2. Clean up any stored name
    const customNames = JSON.parse(localStorage.getItem("complyscan_custom_names") || "{}");
    delete customNames[scanId];
    localStorage.setItem("complyscan_custom_names", JSON.stringify(customNames));

    // 3. Send delete request to backend and refresh dashboard metrics
    try {
        const res = await fetch(`${API_BASE}/api/scans/${scanId}`, {
            method: "DELETE"
        });
        if (res.ok) {
            await loadDashboard();
        }
    } catch (e) {
        console.error("Backend delete failed:", e);
    }
};


// ================================
// FORMAT DATE
// ================================

function formatDate(value) {

    if (!value) {
        return "Date unavailable";
    }

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
        return String(value);
    }

    return date.toLocaleString();
}


// ================================
// ESCAPE HTML
// ================================

function escapeHTML(value) {

    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}


// ================================
// REFRESH BUTTON
// ================================

if (refreshButton) {
    refreshButton.addEventListener(
        "click",
        async () => {

            refreshButton.textContent =
                "↻ Loading...";

            refreshButton.disabled = true;

            await Promise.all([
                loadDashboard(),
                loadScans()
            ]);

            refreshButton.textContent =
                "↻ Refresh";

            refreshButton.disabled = false;
        }
    );
}


// ================================
// INITIAL LOAD
// ================================

loadDashboard();
loadScans();