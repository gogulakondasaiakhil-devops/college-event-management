// ==========================================
// SEND OTP
// ==========================================

function sendOTP() {

    const emailInput = document.getElementById("studentEmail");
    const message = document.getElementById("otpMessage");

    if (!emailInput) {
        console.error("Email input not found");
        return;
    }

    const email = emailInput.value.trim();

    if (email === "") {

        message.style.color = "red";
        message.innerText = "Please enter your email address.";

        return;
    }

    message.style.color = "#2563eb";
    message.innerText = "Sending OTP...";

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

            message.style.color = "green";

            message.innerText =
                "OTP sent successfully to " + email;

        } else {

            message.style.color = "red";

            message.innerText =
                data.message || "Unable to send OTP.";

        }

    })

    .catch(error => {

        console.error("OTP Error:", error);

        message.style.color = "red";

        message.innerText =
            "Unable to send OTP. Check the Flask terminal.";

    });
}


// ==========================================
// VERIFY OTP
// ==========================================
function verifyOTP() {

    const otp = document.getElementById("otp").value.trim();
    const message = document.getElementById("otpMessage");
    const registerButton = document.getElementById("registerButton");

    if (otp === "") {
        message.style.color = "red";
        message.innerText = "Please enter the OTP.";
        return;
    }

    message.style.color = "#2563eb";
    message.innerText = "Verifying OTP...";

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

            message.style.color = "green";
            message.innerText = "✓ OTP verified successfully.";

            registerButton.disabled = false;

        } else {

            message.style.color = "red";
            message.innerText = "✗ Invalid OTP.";

            registerButton.disabled = true;
        }

    })
    .catch(error => {

        console.error(error);

        message.style.color = "red";
        message.innerText = "Unable to verify OTP.";

    });
}