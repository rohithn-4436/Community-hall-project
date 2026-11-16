async function updateStatus(bookingId, status) {
    const message = document.getElementById("adminMessage");

    try {
        const response = await fetch(
            `/admin/booking/${bookingId}/status`,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({ status: status })
            }
        );

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || "Could not update booking.");
        }

        message.textContent = result.message;
        message.style.color = "green";

        // Reload to show the latest booking status and totals.
        window.location.reload();

    } catch (error) {
        message.textContent = error.message;
        message.style.color = "red";
    }
}
