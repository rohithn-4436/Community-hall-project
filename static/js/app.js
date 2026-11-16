
const bookingForm = document.getElementById("bookingForm");
const hallSelect = document.getElementById("hall");
const bookingDate = document.getElementById("date");
const formMessage = document.getElementById("formMessage");

const today = new Date();
const localDate = new Date(
    today.getTime() - today.getTimezoneOffset() * 60000
).toISOString().split("T")[0];

bookingDate.min = localDate;

document.querySelectorAll(".book-button").forEach(button => {
    button.addEventListener("click", () => {
        hallSelect.value = button.dataset.hall;

        document.getElementById("booking").scrollIntoView({
            behavior: "smooth"
        });
    });
});

bookingForm.addEventListener("submit", async event => {
    event.preventDefault();

    const startTime = document.getElementById("startTime").value;
    const endTime = document.getElementById("endTime").value;
    const guests = Number(document.getElementById("guests").value);

    const capacities = {
        "Hall A": 300,
        "Hall B": 150,
        "Hall C": 100
    };

    if (endTime <= startTime) {
        showMessage("Ending time must be after starting time.", "red");
        return;
    }

    if (guests > capacities[hallSelect.value]) {
        showMessage("Guest count exceeds this hall's capacity.", "red");
        return;
    }

    const bookingData = Object.fromEntries(
        new FormData(bookingForm).entries()
    );

    bookingData.guests = guests;

    showMessage("Submitting your booking...", "#2563eb");

    try {
        const response = await fetch("/bookings", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(bookingData)
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || "Booking failed.");
        }

        showMessage(
            `${result.message} Your booking ID is ${result.booking_id}.`,
            "green"
        );

        bookingForm.reset();
        bookingDate.min = localDate;

    } catch (error) {
        showMessage(error.message, "red");
    }
});

function showMessage(message, color) {
    formMessage.textContent = message;
    formMessage.style.color = color;
}
