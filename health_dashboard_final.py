# health_dashboard_final_v3.py
import sys
import os
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, Response

# --- CONFIGURATION (No changes) ---
DB_FILE = 'health.db'
XML_FILE = 'export.xml'
IMPORT_WORKOUTS = True
DATA_TYPES_TO_IMPORT = {
    'HKQuantityTypeIdentifierStepCount', 'HKQuantityTypeIdentifierActiveEnergyBurned', 'HKQuantityTypeIdentifierBasalEnergyBurned',
    'HKQuantityTypeIdentifierHeartRate', 'HKQuantityTypeIdentifierRestingHeartRate', 'HKQuantityTypeIdentifierWalkingHeartRateAverage',
    'HKQuantityTypeIdentifierHeartRateVariabilitySDNN', 'HKQuantityTypeIdentifierOxygenSaturation', 'HKQuantityTypeIdentifierRespiratoryRate',
    'HKQuantityTypeIdentifierBodyTemperature', 'HKQuantityTypeIdentifierBloodPressureSystolic', 'HKQuantityTypeIdentifierBloodPressureDiastolic',
    'HKCategoryTypeIdentifierSleepAnalysis',
}

# --- DATABASE AND IMPORTER LOGIC (No changes) ---
def init_db():
    print("Initializing database...")
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS health_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT, record_type TEXT NOT NULL, unit TEXT,
                record_value REAL NOT NULL, start_date TIMESTAMP NOT NULL)''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_type_date ON health_data (record_type, start_date)')
    print("Database initialized successfully.")

def parse_and_import():
    if not os.path.exists(XML_FILE):
        print(f"Error: {XML_FILE} not found. Please place it in the same directory.")
        return
    init_db()
    print(f"Starting import of {XML_FILE}. This may take a very long time...")
    context = ET.iterparse(XML_FILE, events=('end',))
    records_batch = []
    batch_size = 5000
    count = 0
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM health_data")
        if cursor.fetchone()[0] > 0:
            print("Database already contains data. Skipping import. To re-import, delete the health.db file.")
            return
        for event, elem in context:
            tag = elem.tag
            if tag == 'Record':
                record_type = elem.get('type')
                if record_type in DATA_TYPES_TO_IMPORT:
                    try:
                        if record_type == 'HKCategoryTypeIdentifierSleepAnalysis':
                            sleep_stage_type = elem.get('value')
                            start_date = datetime.strptime(elem.get('startDate'), '%Y-%m-%d %H:%M:%S %z')
                            end_date = datetime.strptime(elem.get('endDate'), '%Y-%m-%d %H:%M:%S %z')
                            duration_minutes = (end_date - start_date).total_seconds() / 60
                            records_batch.append((sleep_stage_type, 'min', duration_minutes, start_date))
                            count += 1
                        else:
                            value = float(elem.get('value'))
                            unit = elem.get('unit')
                            start_date = datetime.strptime(elem.get('startDate'), '%Y-%m-%d %H:%M:%S %z')
                            records_batch.append((record_type, unit, value, start_date))
                            count += 1
                    except (ValueError, TypeError, AttributeError):
                        pass
            elif tag == 'Workout' and IMPORT_WORKOUTS:
                try:
                    energy_burned_elem = elem.find('TotalEnergyBurned')
                    if energy_burned_elem is not None:
                        value = float(energy_burned_elem.get('value'))
                        unit = energy_burned_elem.get('unit')
                        start_date = datetime.strptime(elem.get('startDate'), '%Y-%m-%d %H:%M:%S %z')
                        records_batch.append(('HKQuantityTypeIdentifierActiveEnergyBurned', unit, value, start_date))
                        count += 1
                except (ValueError, TypeError, AttributeError):
                    pass
            if len(records_batch) >= batch_size:
                cursor.executemany('INSERT INTO health_data (record_type, unit, record_value, start_date) VALUES (?, ?, ?, ?)', records_batch)
                conn.commit()
                print(f"Imported {count} records...")
                records_batch = []
            if tag in ['Record', 'Workout', 'ActivitySummary']:
                elem.clear()
        if records_batch:
            cursor.executemany('INSERT INTO health_data (record_type, unit, record_value, start_date) VALUES (?, ?, ?, ?)', records_batch)
            conn.commit()
        print(f"Imported a total of {count} records.")
    print("Import complete!")

# --- FLASK WEB SERVER & API ---

try:
    from waitress import serve
except ImportError:
    serve = None

app = Flask(__name__)

@app.route('/')
def dashboard():
    """Serves the main dashboard HTML page."""
    html_template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Health Dashboard</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2.0.1/dist/chartjs-plugin-zoom.min.js"></script>
        <style>
            :root {
                --bg-color: #f0f2f5;
                --text-color: #1c1e21;
                --card-bg-color: #fff;
                --card-shadow: 0 2px 4px rgba(0,0,0,0.1);
                --header-color: #000;
                --button-bg: #e4e6eb;
                --button-text: #050505;
                --button-active-bg: #007aff;
                --button-active-text: white;
                --chart-grid-color: rgba(0, 0, 0, 0.1);
            }
            body.dark-mode {
                --bg-color: #18191a;
                --text-color: #e4e6eb;
                --card-bg-color: #242526;
                --card-shadow: 0 2px 4px rgba(0,0,0,0.3);
                --header-color: #e4e6eb;
                --button-bg: #3a3b3c;
                --button-text: #e4e6eb;
                --button-active-bg: #2e89ff;
                --button-active-text: white;
                --chart-grid-color: rgba(255, 255, 255, 0.1);
            }
            body { 
                font-family: -apple-system, BlinkMacSystemFont, sans-serif; 
                background-color: var(--bg-color); 
                color: var(--text-color); 
                margin: 0; padding: 20px; 
                transition: background-color 0.3s, color 0.3s;
            }
            .header { text-align: center; margin-bottom: 20px; position: relative; }
            h1 { color: var(--header-color); }
            #date-range-selector button {
                background: var(--button-bg); color: var(--button-text); border: none; border-radius: 6px;
                padding: 8px 12px; margin: 0 5px; cursor: pointer;
                font-family: -apple-system, BlinkMacSystemFont, sans-serif; font-size: 14px;
            }
            #date-range-selector button.active {
                background: var(--button-active-bg); color: var(--button-active-text); font-weight: 600;
            }
            .summary-grid {
                display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px; margin-bottom: 20px;
            }
            .summary-card {
                background-color: var(--card-bg-color); border-radius: 8px;
                box-shadow: var(--card-shadow); padding: 20px; text-align: center;
            }
            .summary-card h2 { margin: 0; font-size: 2.5em; color: var(--header-color); }
            .summary-card p { margin: 5px 0 0; font-size: 0.9em; text-transform: uppercase; }
            .dashboard-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(500px, 1fr)); gap: 20px; }
            .chart-container { background: var(--card-bg-color); border-radius: 8px; box-shadow: var(--card-shadow); padding: 20px; }
            .dark-mode-toggle { position: absolute; top: 10px; right: 20px; }
            .switch{position:relative;display:inline-block;width:60px;height:34px}.switch input{opacity:0;width:0;height:0}.slider{position:absolute;cursor:pointer;top:0;left:0;right:0;bottom:0;background-color:#ccc;-webkit-transition:.4s;transition:.4s}.slider:before{position:absolute;content:"";height:26px;width:26px;left:4px;bottom:4px;background-color:white;-webkit-transition:.4s;transition:.4s}input:checked+.slider{background-color:#2196F3}input:checked+.slider:before{-webkit-transform:translateX(26px);-ms-transform:translateX(26px);transform:translateX(26px)}.slider.round{border-radius:34px}.slider.round:before{border-radius:50%}
        </style>
    </head>
    <body>
        <div class="header">
            <div class="dark-mode-toggle">
                <label class="switch">
                    <input type="checkbox" id="dark-mode-checkbox">
                    <span class="slider round"></span>
                </label>
            </div>
            <h1>Apple Health Dashboard 🍎</h1>
            <div id="date-range-selector">
                <button class="date-btn active" data-days="30">30 Days</button>
                <button class="date-btn" data-days="90">90 Days</button>
                <button class="date-btn" data-days="180">180 Days</button>
                <button class="date-btn" data-days="365">1 Year</button>
            </div>
        </div>

        <div class="summary-grid">
            <div class="summary-card">
                <h2 id="lowest-rhr-value">-</h2><p>Lowest Resting HR</p>
            </div>
            <div class="summary-card">
                <h2 id="avg-steps-value">-</h2><p>Avg Daily Steps</p>
            </div>
            <div class="summary-card">
                <h2 id="avg-sleep-value">-</h2><p>Avg Sleep Time</p>
            </div>
            <div class="summary-card">
                <h2 id="highest-hrv-value">-</h2><p>Highest HRV</p>
            </div>
        </div>

        <div class="dashboard-grid">
            </div>

        <script>
            const baseZoomOptions = { pan: { enabled: true, mode: 'x' }, zoom: { wheel: { enabled: true }, pinch: { enabled: true }, mode: 'x' } };
            // Chart creation functions (createChart, createSleepChart, createBloodPressureChart) go here...
            // These functions are the same as the previous version, just make sure they accept 'days' as an argument.
            
            // --- MAIN DASHBOARD LOGIC ---
            
            function clearDashboard() {
                const grid = document.querySelector('.dashboard-grid');
                grid.innerHTML = `
                    <div class="chart-container"><canvas id="sleepChart"></canvas></div>
                    <div class="chart-container"><canvas id="restingHeartRateChart"></canvas></div>
                    <div class="chart-container"><canvas id="hrvChart"></canvas></div>
                    <div class="chart-container"><canvas id="bloodPressureChart"></canvas></div>
                    <div class="chart-container"><canvas id="respiratoryRateChart"></canvas></div>
                    <div class="chart-container"><canvas id="bodyTempChart"></canvas></div>
                    <div class="chart-container"><canvas id="stepsChart"></canvas></div>
                    <div class="chart-container"><canvas id="activeEnergyChart"></canvas></div>
                    <div class="chart-container"><canvas id="restingEnergyChart"></canvas></div>
                    <div class="chart-container"><canvas id="bloodOxygenChart"></canvas></div>
                `;
            }

            async function loadSummaryCards(days) {
                try {
                    const response = await fetch(`/api/summary?days=${days}`);
                    if (!response.ok) return;
                    const data = await response.json();
                    
                    document.getElementById('lowest-rhr-value').innerText = data.lowest_rhr ? `${Math.round(data.lowest_rhr)} bpm` : '-';
                    document.getElementById('avg-steps-value').innerText = data.avg_steps ? Math.round(data.avg_steps).toLocaleString() : '-';
                    document.getElementById('highest-hrv-value').innerText = data.highest_hrv ? `${Math.round(data.highest_hrv)} ms` : '-';
                    
                    if (data.avg_sleep_minutes) {
                        const hours = Math.floor(data.avg_sleep_minutes / 60);
                        const minutes = Math.round(data.avg_sleep_minutes % 60);
                        document.getElementById('avg-sleep-value').innerText = `${hours}h ${minutes}m`;
                    } else {
                        document.getElementById('avg-sleep-value').innerText = '-';
                    }
                } catch (error) {
                    console.error("Failed to load summary cards:", error);
                }
            }

            function loadAllCharts(days) {
                clearDashboard();
                createSleepChart(days);
                createBloodPressureChart(days);
                createChart('respiratoryRateChart', `/api/data?type=HKQuantityTypeIdentifierRespiratoryRate&days=${days}`, { label: 'Respiratory Rate', borderColor: 'rgb(4, 186, 179)', backgroundColor: 'rgba(4, 186, 179, 0.5)', yAxisLabel: 'breaths/min' });
                createChart('bodyTempChart', `/api/data?type=HKQuantityTypeIdentifierBodyTemperature&days=${days}`, { label: 'Body Temperature', borderColor: 'rgb(255, 128, 0)', backgroundColor: 'rgba(255, 128, 0, 0.5)', yAxisLabel: '°C' });
                createChart('restingEnergyChart', `/api/data?type=HKQuantityTypeIdentifierBasalEnergyBurned&days=${days}&aggregate=sum`, { label: 'Resting Energy Burned', borderColor: 'rgb(75, 192, 192)', backgroundColor: 'rgba(75, 192, 192, 0.5)', yAxisLabel: 'kcal' });
                createChart('bloodOxygenChart', `/api/data?type=HKQuantityTypeIdentifierOxygenSaturation&days=${days}`, { label: 'Blood Oxygen (SpO2)', borderColor: 'rgb(255, 26, 104)', backgroundColor: 'rgba(255, 26, 104, 0.5)', yAxisLabel: '%', transform: (y) => y * 100 });
                createChart('restingHeartRateChart', `/api/data?type=HKQuantityTypeIdentifierRestingHeartRate&days=${days}`, { label: 'Resting Heart Rate', borderColor: 'rgb(255, 99, 132)', backgroundColor: 'rgba(255, 99, 132, 0.5)', yAxisLabel: 'bpm' });
                createChart('stepsChart', `/api/data?type=HKQuantityTypeIdentifierStepCount&days=${days}&aggregate=sum`, { label: 'Daily Steps', borderColor: 'rgb(54, 162, 235)', backgroundColor: 'rgba(54, 162, 235, 0.5)', yAxisLabel: 'Count' });
                createChart('activeEnergyChart', `/api/data?type=HKQuantityTypeIdentifierActiveEnergyBurned&days=${days}&aggregate=sum`, { label: 'Active Energy Burned', borderColor: 'rgb(255, 159, 64)', backgroundColor: 'rgba(255, 159, 64, 0.5)', yAxisLabel: 'kcal' });
                createChart('hrvChart', `/api/data?type=HKQuantityTypeIdentifierHeartRateVariabilitySDNN&days=${days}`, { label: 'Heart Rate Variability (SDNN)', borderColor: 'rgb(153, 102, 255)', backgroundColor: 'rgba(153, 102, 255, 0.5)', yAxisLabel: 'ms' });
            }
            
            function applyTheme(isDark) {
                if (isDark) {
                    document.body.classList.add('dark-mode');
                    Chart.defaults.color = 'rgba(255, 255, 255, 0.7)';
                    Chart.defaults.borderColor = 'rgba(255, 255, 255, 0.1)';
                } else {
                    document.body.classList.remove('dark-mode');
                    Chart.defaults.color = 'rgba(0, 0, 0, 0.7)';
                    Chart.defaults.borderColor = 'rgba(0, 0, 0, 0.1)';
                }
            }
            
            // This function combines all the chart creation logic. It's long but self-contained.
            function initializeChartFunctions() {
                // This is the createChart function from the previous version, now takes 'days'
                window.createChart = async function(canvasId, apiEndpoint, chartConfig) {
                    const ctx = document.getElementById(canvasId).getContext('2d');
                    try {
                        const response = await fetch(apiEndpoint);
                        if (!response.ok) throw new Error(`Network error for ${chartConfig.label}`);
                        const apiData = await response.json();
                        if (apiData.length === 0) { ctx.font = "16px Arial"; ctx.fillText(`No data available for ${chartConfig.label}`, 10, 50); return; }
                        const transform = chartConfig.transform || (y => y);
                        const chartData = { datasets: [{ label: chartConfig.label, data: apiData.map(d => ({ x: d.start_date, y: transform(d.record_value) })), borderColor: chartConfig.borderColor, backgroundColor: chartConfig.backgroundColor, borderWidth: 2, pointRadius: 1.5, tension: 0.1 }] };
                        const minDate = new Date(apiData[0].start_date);
                        const maxDate = new Date(apiData[apiData.length - 1].start_date);
                        new Chart(ctx, { type: 'line', data: chartData, options: { responsive: true, scales: { x: { type: 'time', min: minDate, max: maxDate, time: { unit: 'day', displayFormats: { day: 'EEE dd.MM.yy' } } }, y: { beginAtZero: false, title: { display: true, text: chartConfig.yAxisLabel } } }, plugins: { zoom: { ...baseZoomOptions, limits: { x: { min: minDate, max: maxDate } } } } } });
                    } catch (error) { console.error(`Failed to load data for ${chartConfig.label}:`, error); ctx.font = "16px Arial"; ctx.fillText(`Could not load chart: ${error.message}`, 10, 50); }
                };
                
                // This is the createSleepChart function, now takes 'days'
                window.createSleepChart = async function(days) {
                    const ctx = document.getElementById('sleepChart').getContext('2d');
                    try {
                        const response = await fetch(`/api/sleep?days=${days}`);
                        if (!response.ok) throw new Error('Network error for Sleep Data');
                        const sleepData = await response.json();
                        if (sleepData.labels.length === 0) { ctx.font = "16px Arial"; ctx.fillText(`No data available for Sleep`, 10, 50); return; }
                        const stageConfig = { 'HKCategoryValueSleepAnalysisAwake': { label: 'Awake', backgroundColor: 'rgba(255, 99, 132, 0.7)' }, 'HKCategoryValueSleepAnalysisAsleepREM': { label: 'REM', backgroundColor: 'rgba(54, 162, 235, 0.7)' }, 'HKCategoryValueSleepAnalysisAsleepCore': { label: 'Core', backgroundColor: 'rgba(75, 192, 192, 0.7)' }, 'HKCategoryValueSleepAnalysisAsleepDeep': { label: 'Deep', backgroundColor: 'rgba(153, 102, 255, 0.7)' } };
                        const datasets = Object.keys(stageConfig).map(stageKey => ({ label: stageConfig[stageKey].label, backgroundColor: stageConfig[stageKey].backgroundColor, data: sleepData.labels.map(date => sleepData.stages[stageKey][date] || 0) }));
                        const minDate = new Date(sleepData.labels[0]);
                        const maxDate = new Date(sleepData.labels[sleepData.labels.length - 1]);
                        new Chart(ctx, { type: 'bar', data: { labels: sleepData.labels, datasets: datasets }, options: { responsive: true, scales: { x: { stacked: true, type: 'time', min: minDate, max: maxDate, time: { unit: 'day', displayFormats: { day: 'EEE dd.MM.yy' } } }, y: { stacked: true, title: { display: true, text: 'Minutes' } } }, plugins: { zoom: { ...baseZoomOptions, limits: { x: { min: minDate, max: maxDate } } } } } });
                    } catch (error) { console.error('Failed to load data for Sleep Chart:', error); ctx.font = "16px Arial"; ctx.fillText(`Could not load chart: ${error.message}`, 10, 50); }
                };

                // This is the createBloodPressureChart function, now takes 'days'
                window.createBloodPressureChart = async function(days) {
                    const ctx = document.getElementById('bloodPressureChart').getContext('2d');
                    try {
                        const [systolicResponse, diastolicResponse] = await Promise.all([ fetch(`/api/data?type=HKQuantityTypeIdentifierBloodPressureSystolic&days=${days}`), fetch(`/api/data?type=HKQuantityTypeIdentifierBloodPressureDiastolic&days=${days}`) ]);
                        if (!systolicResponse.ok || !diastolicResponse.ok) throw new Error('Network error for Blood Pressure');
                        const systolicData = await systolicResponse.json();
                        const diastolicData = await diastolicResponse.json();
                        if (systolicData.length === 0 && diastolicData.length === 0) { ctx.font = "16px Arial"; ctx.fillText(`No data available for Blood Pressure`, 10, 50); return; }
                        const chartData = { datasets: [ { label: 'Systolic', data: systolicData.map(d => ({x: d.start_date, y: d.record_value})), borderColor: 'rgb(255, 99, 132)', backgroundColor: 'rgba(255, 99, 132, 0.5)', borderWidth: 2, pointRadius: 2.5, tension: 0.1 }, { label: 'Diastolic', data: diastolicData.map(d => ({x: d.start_date, y: d.record_value})), borderColor: 'rgb(54, 162, 235)', backgroundColor: 'rgba(54, 162, 235, 0.5)', borderWidth: 2, pointRadius: 2.5, tension: 0.1 } ] };
                        const allDates = [ ...systolicData.map(d => new Date(d.start_date)), ...diastolicData.map(d => new Date(d.start_date)) ];
                        const minDate = new Date(Math.min(...allDates));
                        const maxDate = new Date(Math.max(...allDates));
                        new Chart(ctx, { type: 'line', data: chartData, options: { responsive: true, scales: { x: { type: 'time', min: minDate, max: maxDate, time: { unit: 'day', displayFormats: { day: 'EEE dd.MM.yy' } } }, y: { beginAtZero: false, title: { display: true, text: 'mmHg' } } }, plugins: { zoom: { ...baseZoomOptions, limits: { x: { min: minDate, max: maxDate } } } } } });
                    } catch (error) { console.error('Failed to load data for Blood Pressure Chart:', error); ctx.font = "16px Arial"; ctx.fillText(`Could not load chart: ${error.message}`, 10, 50); }
                };
            }

            document.addEventListener('DOMContentLoaded', () => {
                initializeChartFunctions();
                
                const dateRangeSelector = document.getElementById('date-range-selector');
                const darkModeCheckbox = document.getElementById('dark-mode-checkbox');
                let currentDays = document.querySelector('.date-btn.active').dataset.days;

                function loadDashboard(days) {
                    loadSummaryCards(days);
                    loadAllCharts(days);
                }

                // Dark Mode Logic
                const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
                const savedTheme = localStorage.getItem('theme');
                const isDark = savedTheme ? savedTheme === 'dark' : prefersDark;
                darkModeCheckbox.checked = isDark;
                applyTheme(isDark);
                
                darkModeCheckbox.addEventListener('change', () => {
                    const isChecked = darkModeCheckbox.checked;
                    localStorage.setItem('theme', isChecked ? 'dark' : 'light');
                    applyTheme(isChecked);
                    loadDashboard(currentDays); // Reload charts with new theme
                });
                
                // Date Range Logic
                dateRangeSelector.addEventListener('click', (event) => {
                    if (event.target.tagName === 'BUTTON') {
                        dateRangeSelector.querySelectorAll('.date-btn').forEach(btn => btn.classList.remove('active'));
                        event.target.classList.add('active');
                        currentDays = event.target.dataset.days;
                        loadDashboard(currentDays);
                    }
                });

                // Initial Load
                loadDashboard(currentDays);
            });
        </script>
    </body>
    </html>
    """
    return Response(html_template)

@app.route('/api/data')
def get_data():
    data_type = request.args.get('type')
    days = int(request.args.get('days', 30))
    aggregate = request.args.get('aggregate')
    if not data_type: return jsonify({"error": "Missing 'type' parameter"}), 400
    start_date = datetime.now() - timedelta(days=days)
    params = [data_type, start_date]
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if aggregate == 'sum':
            query = """SELECT date(start_date) as start_date, SUM(record_value) as record_value FROM health_data WHERE record_type = ? AND start_date >= ? GROUP BY date(start_date) ORDER BY start_date;"""
        elif aggregate == 'avg':
            query = """SELECT date(start_date) as start_date, AVG(record_value) as record_value FROM health_data WHERE record_type = ? AND start_date >= ? GROUP BY date(start_date) ORDER BY start_date;"""
        else:
            query = """SELECT start_date, record_value FROM health_data WHERE record_type = ? AND start_date >= ? ORDER BY start_date;"""
        cursor.execute(query, params)
        data = [dict(row) for row in cursor.fetchall()]
        return jsonify(data)

@app.route('/api/sleep')
def get_sleep_data():
    days = int(request.args.get('days', 30))
    start_date = datetime.now() - timedelta(days=days)
    query = """
        SELECT date(start_date) as sleep_date, record_type, SUM(record_value) as total_minutes
        FROM health_data WHERE record_type IN (
            'HKCategoryValueSleepAnalysisAsleepDeep', 'HKCategoryValueSleepAnalysisAsleepCore',
            'HKCategoryValueSleepAnalysisAsleepREM', 'HKCategoryValueSleepAnalysisAwake'
        ) AND start_date >= ? GROUP BY sleep_date, record_type ORDER BY sleep_date;"""
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(query, [start_date])
        sleep_stages = {
            'HKCategoryValueSleepAnalysisAwake': {}, 'HKCategoryValueSleepAnalysisAsleepREM': {},
            'HKCategoryValueSleepAnalysisAsleepCore': {}, 'HKCategoryValueSleepAnalysisAsleepDeep': {},
        }
        dates = set()
        for row in cursor.fetchall():
            row_dict = dict(row)
            date, record_type, total_minutes = row_dict['sleep_date'], row_dict['record_type'], row_dict['total_minutes']
            if record_type in sleep_stages:
                sleep_stages[record_type][date] = total_minutes
                dates.add(date)
        sorted_dates = sorted(list(dates))
        return jsonify({'labels': sorted_dates, 'stages': sleep_stages})

# --- NEW: API Endpoint for Summary Cards ---
@app.route('/api/summary')
def get_summary_data():
    days = int(request.args.get('days', 90))
    start_date = datetime.now() - timedelta(days=days)
    
    summary = {}
    
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()

        # Lowest Resting HR
        cursor.execute("SELECT MIN(record_value) FROM health_data WHERE record_type = 'HKQuantityTypeIdentifierRestingHeartRate' AND start_date >= ?", [start_date])
        summary['lowest_rhr'] = cursor.fetchone()[0]

        # Average Daily Steps
        cursor.execute("""
            SELECT AVG(daily_total) FROM (
                SELECT SUM(record_value) as daily_total 
                FROM health_data 
                WHERE record_type = 'HKQuantityTypeIdentifierStepCount' AND start_date >= ? 
                GROUP BY date(start_date)
            )
        """, [start_date])
        summary['avg_steps'] = cursor.fetchone()[0]

        # Highest HRV
        cursor.execute("SELECT MAX(record_value) FROM health_data WHERE record_type = 'HKQuantityTypeIdentifierHeartRateVariabilitySDNN' AND start_date >= ?", [start_date])
        summary['highest_hrv'] = cursor.fetchone()[0]
        
        # Average Sleep
        sleep_types = ['HKCategoryValueSleepAnalysisAsleepDeep', 'HKCategoryValueSleepAnalysisAsleepCore', 'HKCategoryValueSleepAnalysisAsleepREM']
        placeholders = ','.join('?' for _ in sleep_types)
        cursor.execute(f"""
            SELECT AVG(daily_total) FROM (
                SELECT SUM(record_value) as daily_total 
                FROM health_data 
                WHERE record_type IN ({placeholders}) AND start_date >= ? 
                GROUP BY date(start_date)
            )
        """, sleep_types + [start_date])
        summary['avg_sleep_minutes'] = cursor.fetchone()[0]

    return jsonify(summary)

# --- MAIN EXECUTION ---
def print_usage():
    print("Usage: python your_script_name.py [command]")
    print("Commands:")
    print("  import   - Parse export.xml and load data into the database.")
    print("  serve    - Run the web server to view the dashboard.")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)
    command = sys.argv[1]
    if command == 'import':
        parse_and_import()
    elif command == 'serve':
        if not os.path.exists(DB_FILE):
            print(f"Database file '{DB_FILE}' not found. Run the 'import' command first.")
            sys.exit(1)
        if serve:
            print("Starting web server on http://0.0.0.0:8080")
            serve(app, host='0.0.0.0', port=8080)
        else:
            print("---\n[WARNING] 'waitress' is not installed. Falling back to the basic Flask server.")
            print("For better performance, please run: pip install waitress\n---")
            print("Starting web server on http://0.0.0.0:8080")
            app.run(host='0.0.0.0', port=8080, debug=False)
    else:
        print(f"Unknown command: {command}")
        print_usage()
