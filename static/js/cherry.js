window.addEventListener("DOMContentLoaded", function () {
   // Global references to chart instances
  let barChartInstance = null;
  let lineChartInstance = null;

  // Chart 1 - Static Bar Chart
  const chartBarsElement = document.getElementById("chart-bars");
  if (chartBarsElement) {
    const ctx = chartBarsElement.getContext("2d");

     if (window.barChartInstance) {
      window.barChartInstance.destroy();
    }


    new Chart(ctx, {
      type: "bar",
      data: {
        labels: ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        datasets: [{
          label: "Sales",
          tension: 0.4,
          borderWidth: 0,
          borderRadius: 4,
          borderSkipped: false,
          backgroundColor: "#fff",
          data: [450, 200, 100, 220, 500, 100, 400, 230, 500],
          maxBarThickness: 6,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
        },
        interaction: {
          intersect: false,
          mode: "index",
        },
        scales: {
          y: {
            grid: { drawBorder: false, display: false, drawOnChartArea: false, drawTicks: false },
            ticks: {
              suggestedMin: 0,
              suggestedMax: 600,
              beginAtZero: true,
              padding: 15,
              font: {
                size: 14,
                family: "Open Sans",
                style: "normal",
                lineHeight: 2,
              },
              color: "#fff",
            },
          },
          x: {
            grid: { drawBorder: false, display: false, drawOnChartArea: false, drawTicks: false },
            ticks: { display: false },
          },
        },
      },
    });
  }

  // Chart 2 - Dynamic Line Chart with Data
  const chartLineElement = document.getElementById("chart-line");
  const dataElement = document.getElementById("monthly-orders-data");

  if (chartLineElement && dataElement) {
    const ctx1 = chartLineElement.getContext("2d");

     if (window.lineChartInstance) {
      window.lineChartInstance.destroy();
    }
    
    const gradientStroke1 = ctx1.createLinearGradient(0, 230, 0, 50);
    gradientStroke1.addColorStop(1, 'rgba(94, 114, 228, 0.2)');
    gradientStroke1.addColorStop(0.2, 'rgba(94, 114, 228, 0.0)');
    gradientStroke1.addColorStop(0, 'rgba(94, 114, 228, 0)');

    const orderData = JSON.parse(dataElement.textContent);
    const orderLabels = orderData.map(item => item[0]);
    const orderValues = orderData.map(item => item[1]);

    new Chart(ctx1, {
      type: "line",
      data: {
        labels: orderLabels,
        datasets: [{
          label: "Total Orders",
          tension: 0.4,
          borderWidth: 0,
          pointRadius: 0,
          borderColor: "#5e72e4",
          backgroundColor: gradientStroke1,
          borderWidth: 3,
          fill: true,
          data: orderValues,
          maxBarThickness: 6
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
        },
        interaction: {
          intersect: false,
          mode: 'index',
        },
        scales: {
          y: {
            grid: {
              drawBorder: false,
              display: true,
              drawOnChartArea: true,
              drawTicks: false,
              borderDash: [5, 5]
            },
            ticks: {
              display: true,
              padding: 10,
              color: '#fbfbfb',
              font: {
                size: 11,
                family: "Open Sans",
                style: 'normal',
                lineHeight: 2
              },
            }
          },
          x: {
            grid: {
              drawBorder: false,
              display: false,
              drawOnChartArea: false,
              drawTicks: false,
              borderDash: [5, 5]
            },
            ticks: {
              display: true,
              color: '#ccc',
              padding: 20,
              font: {
                size: 11,
                family: "Open Sans",
                style: 'normal',
                lineHeight: 2
              },
            }
          },
        },
      },
    });
  } else {
    if (!chartLineElement) console.warn("chart-line element not found.");
    if (!dataElement) console.warn("monthly-orders-data element not found.");
  }
});
