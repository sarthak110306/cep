// Flask-integrated login page helpers (no localStorage auth)

let loginType = "user";

// --------------------------------------------------
// Hide all modal views
// --------------------------------------------------

function hideAllModalViews() {
    document.getElementById("loginFormView").style.display = "none";
    document.getElementById("signUpFormView").style.display = "none";
    document.getElementById("signUpSuccessView").style.display = "none";
    document.getElementById("welcomeView").style.display = "none";
}


// --------------------------------------------------
// Login
// --------------------------------------------------

function showLoginForm(e) {
    if (e) e.preventDefault();

    hideAllModalViews();

    document.getElementById("loginFormView").style.display = "block";

    const signupLink = document.getElementById("loginSignupLink");
    if (signupLink) {
        signupLink.style.display = "block";
    }

    const title = document.getElementById("loginTitle");
    if (title) {
        title.innerText = "User Login";
    }

    const hint = document.getElementById("loginHint");
    if (hint) {
        hint.innerText = "Login to register your team";
    }
}


function showSignUp(e) {
    if (e) e.preventDefault();

    hideAllModalViews();

    document.getElementById("signUpFormView").style.display = "block";
}


function openLogin() {
    loginType = "user";

    document.getElementById("loginModal").classList.add("active");

    showLoginForm();
}


function Adminlogin() {
    window.location.href = "/admin/login";
}


function closeLogin() {
    document.getElementById("loginModal").classList.remove("active");

    hideAllModalViews();

    document.getElementById("loginFormView").style.display = "block";
}


// --------------------------------------------------
// NOTE: Forgot-password / OTP verification / reset-password flow removed.
//
// The OTP-based password reset implementation (and its supporting
// getCSRFToken() helper, doForgotPasswordContinue(), verifyResetOtp(),
// doResetPassword(), backToForgotPassword(), backToLogin(), and the OTP
// input-restriction listener that lived here) called Flask routes that
// have been reverted at the project owner's request.
//
// The original pre-OTP password-reset implementation could not be
// recovered from this project (no git history or backup copy was found),
// so no replacement has been invented. See the project report for details.
// The login and signup forms below are plain server-rendered POST forms
// and are unaffected by this removal.
// --------------------------------------------------


// --------------------------------------------------
// Close modal by clicking outside
// --------------------------------------------------

const loginModal = document.getElementById("loginModal");

if (loginModal) {
    loginModal.addEventListener("click", function (e) {
        if (e.target === this) {
            closeLogin();
        }
    });
}
