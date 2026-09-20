
// Detect if running locally on a dev server (e.g. port 3000 or 5500) or directly on Vercel
const isLocalStaticDev = (window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost")
    && window.location.port !== "8000";

const API_BASE = isLocalStaticDev ? "http://127.0.0.1:8000" : "";
const API_BASE_URL = API_BASE;

const scanForm = document.getElementById("scanForm");
const labelImage = document.getElementById("labelImage");
const previewContainer = document.getElementById("previewContainer");
const previewImage = document.getElementById("previewImage");
const scanButton = document.getElementById("scanButton");
const loadingMessage = document.getElementById("loadingMessage");
const errorMessage = document.getElementById("errorMessage");

const dropArea = document.getElementById("dropArea");
const removeImage = document.getElementById("removeImage");

let previewURL = null;


/* ================= IMAGE PREVIEW ================= */

function handleImage(file) {

    if (!file) {
        previewContainer.style.display = "none";
        return;
    }

    if (!file.type.startsWith("image/")) {
        showError("Please select a valid image file.");
        labelImage.value = "";
        previewContainer.style.display = "none";
        return;
    }

    if (previewURL) {
        URL.revokeObjectURL(previewURL);
    }

    previewURL = URL.createObjectURL(file);

    previewImage.src = previewURL;
    previewContainer.style.display = "block";

    hideError();
}


/* ================= FILE SELECT ================= */

labelImage.addEventListener("change", function () {

    const file = labelImage.files[0];

    handleImage(file);

});


/* ================= DRAG & DROP ================= */

dropArea.addEventListener("dragover", function (event) {

    event.preventDefault();

    dropArea.classList.add("dragover");

});


dropArea.addEventListener("dragleave", function () {

    dropArea.classList.remove("dragover");

});


dropArea.addEventListener("drop", function (event) {

    event.preventDefault();

    dropArea.classList.remove("dragover");

    const file = event.dataTransfer.files[0];

    if (!file) {
        return;
    }

    const dataTransfer = new DataTransfer();

    dataTransfer.items.add(file);

    labelImage.files = dataTransfer.files;

    handleImage(file);

});


/* ================= REMOVE IMAGE ================= */

removeImage.addEventListener("click", function () {

    labelImage.value = "";

    previewImage.src = "";

    previewContainer.style.display = "none";

    if (previewURL) {
        URL.revokeObjectURL(previewURL);
        previewURL = null;
    }

    hideError();

});


/* ================= FORM SUBMIT ================= */

scanForm.addEventListener("submit", async function (event) {

    event.preventDefault();

    const file = labelImage.files[0];

    if (!file) {
        showError("Please select a label image first.");
        return;
    }

    hideError();

    loadingMessage.style.display = "flex";

    scanButton.disabled = true;
    scanButton.textContent = "Scanning...";


    try {

        const formData = new FormData();

        formData.append("file", file);


        const response = await fetch(`${API_BASE}/api/scan`, {
            method: "POST",
            body: formData
        });


        if (!response.ok) {

            let message = "Something went wrong while scanning.";

            try {

                const errorData = await response.json();

                if (errorData.detail) {
                    message = errorData.detail;
                }

            } catch (error) {
                // Keep default error message
            }

            throw new Error(message);
        }


        const result = await response.json();


        sessionStorage.setItem(
            "complyscan-result",
            JSON.stringify(result)
        );


        if (result.id) {

            window.location.href =
                `report.html?id=${encodeURIComponent(result.id)}`;

        } else {

            window.location.href = "report.html";

        }


    } catch (error) {

        console.error(error);

        if (error.message === "Failed to fetch") {

            showError(
                "Could not connect to the server. Please make sure the backend is running."
            );

        } else {

            showError(
                error.message ||
                "Unable to scan the label. Please try again."
            );

        }

    } finally {

        loadingMessage.style.display = "none";

        scanButton.disabled = false;

        scanButton.textContent = "Upload & Scan →";

    }

});


/* ================= ERROR ================= */

function showError(message) {

    errorMessage.textContent = message;

    errorMessage.style.display = "block";

}


function hideError() {

    errorMessage.textContent = "";

    errorMessage.style.display = "none";

}

