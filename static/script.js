// ==========================================
// SEND OTP
// ==========================================

function sendOTP() {

    const emailInput = document.getElementById("studentEmail") || document.getElementById("email");
    const message = document.getElementById("otpMessage");

    if (!emailInput) {
        console.error("Email input not found");
        return;
    }

    const email = emailInput.value.trim();

    if (email === "") {
        if (message) {
            message.style.color = "red";
            message.innerText = "Please enter your email address.";
        } else {
            alert("Please enter your email address.");
        }
        return;
    }

    if (message) {
        message.style.color = "#2563eb";
        message.innerText = "Sending OTP...";
    }

    fetch("/send-otp", {
        method: "POST",
        headers: {
            "Content-Type": "application/x-www-form-urlencoded"
        },
        body: "email=" + encodeURIComponent(email)
    })
    .then(response => {
        if (!response.ok) {
            throw new Error("Server error: " + response.status);
        }
        return response.json();
    })
    .then(data => {
        console.log("OTP response:", data);
        if (data.status === "success") {
            if (message) {
                message.style.color = "green";
                message.innerText = "OTP sent successfully to " + email;
            }
            const otpSection = document.getElementById("otpSection");
            if (otpSection) {
                otpSection.style.display = "block";
            }
        } else {
            if (message) {
                message.style.color = "red";
                message.innerText = data.message || "Unable to send OTP.";
            }
        }
    })
    .catch(error => {
        console.error("OTP Error:", error);
        if (message) {
            message.style.color = "red";
            message.innerText = "Unable to send OTP. Check the Flask terminal.";
        }
    });
}


// ==========================================
// VERIFY OTP
// ==========================================
function verifyOTP(isRedirectOnSuccess = false) {

    const otpElem = document.getElementById("otp") || document.getElementById("otpInput");
    const message = document.getElementById("otpMessage");
    const registerButton = document.getElementById("registerButton");

    if (!otpElem) {
        console.error("OTP input not found");
        return;
    }

    const otp = otpElem.value.trim();

    if (otp === "") {
        if (message) {
            message.style.color = "red";
            message.innerText = "Please enter the OTP.";
        }
        return;
    }

    if (message) {
        message.style.color = "#2563eb";
        message.innerText = "Verifying OTP...";
    }

    fetch("/verify-otp", {
        method: "POST",
        headers: {
            "Content-Type": "application/x-www-form-urlencoded"
        },
        body: "otp=" + encodeURIComponent(otp)
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === "verified") {
            if (message) {
                message.style.color = "green";
                message.innerText = "✓ OTP verified successfully.";
            }
            if (registerButton) {
                registerButton.disabled = false;
            }
            if (isRedirectOnSuccess) {
                setTimeout(() => {
                    window.location.href = "/dashboard.html";
                }, 1000);
            }
        } else {
            if (message) {
                message.style.color = "red";
                message.innerText = "✗ Invalid OTP.";
            }
            if (registerButton) {
                registerButton.disabled = true;
            }
        }
    })
    .catch(error => {
        console.error(error);
        if (message) {
            message.style.color = "red";
            message.innerText = "Unable to verify OTP.";
        }
    });
}

function login() {
    verifyOTP(true);
}