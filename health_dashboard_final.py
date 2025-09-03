# health_dashboard_final.py
import sys
import os
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, Response

# --- CONFIGURATION ---
DB_FILE = 'health.db'
XML_FILE = 'export.xml'
IMPORT_WORKOUTS = True

# A comprehensive list of data types to import
DATA_TYPES_TO_IMPORT = {
    # Activity
    'HKQuantityTypeIdentifierStepCount',
    'HKQuantityTypeIdentifierActiveEnergyBurned',
    'HKQuantityTypeIdentifierBasalEnergyBurned',
    
    # Vitals
    'HKQuantityTypeIdentifierHeartRate',
    'HKQuantityTypeIdentifierRestingHeartRate',
    'HKQuantityTypeIdentifierWalkingHeartRateAverage',
    'HKQuantityTypeIdentifierHeartRateVariabilitySDNN',
    'HKQuantityTypeIdentifierOxygenSaturation',
    'HKQuantityTypeIdentifierRespiratoryRate',
    'HKQuantityTypeIdentifierBodyTemperature',
    'HKQuantityTypeIdentifierBloodPressureSystolic',
    'HKQuantityTypeIdentifierBloodPressureDiastolic',

    # Sleep
    'HKCategoryTypeIdentifierSleepAnalysis',
}

# --- DATABASE AND IMPORTER LOGIC ---

def init_db():
    """Initializes the database and creates the table if it doesn't exist."""
    print("Initializing database...")
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS health_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_type TEXT NOT NULL,
                unit TEXT,
                record_value REAL NOT NULL,
                start_date TIMESTAMP NOT NULL
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_type_date ON health_data (record_type, start_date)')
    print("Database initialized successfully.")

def parse_and_import():
    """Parses the export.xml file and imports the data into the SQLite DB."""
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
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background-color: #f0f2f5; color: #1c1e21; margin: 0; padding: 20px; }
            h1 { text-align: center; color: #000; }
            .dashboard-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(500px, 1fr)); gap: 20px; }
            .chart-container { background: #fff; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); padding: 20px; }
        </style>
    </head>
    <body>
        <h1>Apple Health Dashboard 🍎</h1>
        <div class="dashboard-grid">
            <div class="chart-container">
                <canvas id="sleepChart"></canvas>
            </div>
            <div class="chart-container">
                <canvas id="restingHeartRateChart"></canvas>
            </div>
             <div class="chart-container">
                <canvas id="hrvChart"></canvas>
            </div>
            <div class="chart-container">
                <canvas id="bloodPressureChart"></canvas>
            </div>
            <div class="chart-container">
                <canvas id="respiratoryRateChart"></canvas>
            </div>
            <div class="chart-container">
                <canvas id="bodyTempChart"></canvas>
            </div>
            <div class="chart-container">
                <canvas id="stepsChart"></canvas>
            </div>
            <div class="chart-container">
                <canvas id="activeEnergyChart"></canvas>
            </div>
            <div class="chart-container">
                <canvas id="restingEnergyChart"></canvas>
            </div>
            <div class="chart-container">
                <canvas id="bloodOxygenChart"></canvas>
            </div>
        </div>

        <script>
            async function createChart(canvasId, apiEndpoint, chartConfig) {
                const ctx = document.getElementById(canvasId).getContext('2d');
                try {
                    const response = await fetch(apiEndpoint);
                    if (!response.ok) throw new Error(`Network response was not ok for ${chartConfig.label}`);
                    const apiData = await response.json();
                    if (apiData.length === 0) {
                        ctx.font = "16px Arial";
                        ctx.fillText(`No data available for ${chartConfig.label}`, 10, 50);
                        return;
                    }
                    const transform = chartConfig.transform || (y => y);
                    const chartData = {
                        datasets: [{
                            label: chartConfig.label,
                            data: apiData.map(d => ({ x: d.start_date, y: transform(d.record_value) })),
                            borderColor: chartConfig.borderColor,
                            backgroundColor: chartConfig.backgroundColor,
                            borderWidth: 2, pointRadius: 1.5, tension: 0.1
                        }]
                    };
                    new Chart(ctx, { type: 'line', data: chartData,
                        options: { responsive: true, scales: { x: { type: 'time', time: { unit: 'day' } }, y: { beginAtZero: false, title: { display: true, text: chartConfig.yAxisLabel } } } }
                    });
                } catch (error) {
                    console.error(`Failed to load data for ${chartConfig.label}:`, error);
                    ctx.font = "16px Arial";
                    ctx.fillText(`Could not load chart: ${error.message}`, 10, 50);
                }
            }

            async function createSleepChart() {
                const ctx = document.getElementById('sleepChart').getContext('2d');
                try {
                    const response = await fetch('/api/sleep?days=90');
                    if (!response.ok) throw new Error('Network response for Sleep Data');
                    const sleepData = await response.json();
                     if (sleepData.labels.length === 0) {
                        ctx.font = "16px Arial";
                        ctx.fillText(`No data available for Sleep`, 10, 50);
                        return;
                    }
                    const stageConfig = {
                        'HKCategoryValueSleepAnalysisAwake': { label: 'Awake', backgroundColor: 'rgba(255, 99, 132, 0.7)' },
                        'HKCategoryValueSleepAnalysisAsleepREM': { label: 'REM', backgroundColor: 'rgba(54, 162, 235, 0.7)' },
                        'HKCategoryValueSleepAnalysisAsleepCore': { label: 'Core', backgroundColor: 'rgba(75, 192, 192, 0.7)' },
                        'HKCategoryValueSleepAnalysisAsleepDeep': { label: 'Deep', backgroundColor: 'rgba(153, 102, 255, 0.7)' },
                    };
                    const datasets = Object.keys(stageConfig).map(stageKey => ({
                        label: stageConfig[stageKey].label, backgroundColor: stageConfig[stageKey].backgroundColor,
                        data: sleepData.labels.map(date => sleepData.stages[stageKey][date] || 0)
                    }));
                    new Chart(ctx, { type: 'bar', data: { labels: sleepData.labels, datasets: datasets },
                        options: { responsive: true, scales: { x: { stacked: true, type: 'time', time: { unit: 'day' } }, y: { stacked: true, title: { display: true, text: 'Minutes' } } } }
                    });
                } catch (error) {
                    console.error('Failed to load data for Sleep Chart:', error);
                    ctx.font = "16px Arial";
                    ctx.fillText(`Could not load chart: ${error.message}`, 10, 50);
                }
            }
            
            async function createBloodPressureChart() {
                const ctx = document.getElementById('bloodPressureChart').getContext('2d');
                const days = 90;
                try {
                    const [systolicResponse, diastolicResponse] = await Promise.all([
                        fetch(`/api/data?type=HKQuantityTypeIdentifierBloodPressureSystolic&days=${days}`),
                        fetch(`/api/data?type=HKQuantityTypeIdentifierBloodPressureDiastolic&days=${days}`)
                    ]);
                    if (!systolicResponse.ok || !diastolicResponse.ok) throw new Error('Network response for Blood Pressure');
                    const systolicData = await systolicResponse.json();
                    const diastolicData = await diastolicResponse.json();
                    if (systolicData.length === 0 && diastolicData.length === 0) {
                        ctx.font = "16px Arial";
                        ctx.fillText(`No data available for Blood Pressure`, 10, 50);
                        return;
                    }
                    const chartData = {
                        datasets: [
                            { label: 'Systolic', data: systolicData.map(d => ({x: d.start_date, y: d.record_value})), borderColor: 'rgb(255, 99, 132)', backgroundColor: 'rgba(255, 99, 132, 0.5)', borderWidth: 2, pointRadius: 2.5, tension: 0.1 },
                            { label: 'Diastolic', data: diastolicData.map(d => ({x: d.start_date, y: d.record_value})), borderColor: 'rgb(54, 162, 235)', backgroundColor: 'rgba(54, 162, 235, 0.5)', borderWidth: 2, pointRadius: 2.5, tension: 0.1 }
                        ]
                    };
                    new Chart(ctx, { type: 'line', data: chartData, 
                        options: { responsive: true, scales: { x: { type: 'time', time: { unit: 'day' } }, y: { beginAtZero: false, title: { display: true, text: 'mmHg' } } } }
                    });
                } catch (error) {
                    console.error('Failed to load data for Blood Pressure Chart:', error);
                    ctx.font = "16px Arial";
                    ctx.fillText(`Could not load chart: ${error.message}`, 10, 50);
                }
            }

            document.addEventListener('DOMContentLoaded', () => {
                const days = 90;

                // Call all chart creation functions
                createSleepChart();
                createBloodPressureChart();

                createChart('respiratoryRateChart', `/api/data?type=HKQuantityTypeIdentifierRespiratoryRate&days=${days}`, 
                    { label: 'Respiratory Rate', borderColor: 'rgb(4, 186, 179)', backgroundColor: 'rgba(4, 186, 179, 0.5)', yAxisLabel: 'breaths/min' });
                
                createChart('bodyTempChart', `/api/data?type=HKQuantityTypeIdentifierBodyTemperature&days=${days}`, 
                    { label: 'Body Temperature', borderColor: 'rgb(255, 128, 0)', backgroundColor: 'rgba(255, 128, 0, 0.5)', yAxisLabel: '°C' });

                createChart('restingEnergyChart', `/api/data?type=HKQuantityTypeIdentifierBasalEnergyBurned&days=${days}&aggregate=sum`, 
                    { label: 'Resting Energy Burned', borderColor: 'rgb(75, 192, 192)', backgroundColor: 'rgba(75, 192, 192, 0.5)', yAxisLabel: 'kcal' });
                
                createChart('bloodOxygenChart', `/api/data?type=HKQuantityTypeIdentifierOxygenSaturation&days=${days}`, 
                    { label: 'Blood Oxygen (SpO2)', borderColor: 'rgb(255, 26, 104)', backgroundColor: 'rgba(255, 26, 104, 0.5)', yAxisLabel: '%', transform: (y) => y * 100 });
                
                createChart('restingHeartRateChart', `/api/data?type=HKQuantityTypeIdentifierRestingHeartRate&days=${days}`, 
                    { label: 'Resting Heart Rate', borderColor: 'rgb(255, 99, 132)', backgroundColor: 'rgba(255, 99, 132, 0.5)', yAxisLabel: 'bpm' });
                
                createChart('stepsChart', `/api/data?type=HKQuantityTypeIdentifierStepCount&days=${days}&aggregate=sum`, 
                    { label: 'Daily Steps', borderColor: 'rgb(54, 162, 235)', backgroundColor: 'rgba(54, 162, 235, 0.5)', yAxisLabel: 'Count' });
                
                createChart('activeEnergyChart', `/api/data?type=HKQuantityTypeIdentifierActiveEnergyBurned&days=${days}&aggregate=sum`, 
                    { label: 'Active Energy Burned', borderColor: 'rgb(255, 159, 64)', backgroundColor: 'rgba(255, 159, 64, 0.5)', yAxisLabel: 'kcal' });
                
                createChart('hrvChart', `/api/data?type=HKQuantityTypeIdentifierHeartRateVariabilitySDNN&days=${days}`, 
                    { label: 'Heart Rate Variability (SDNN)', borderColor: 'rgb(153, 102, 255)', backgroundColor: 'rgba(153, 102, 255, 0.5)', yAxisLabel: 'ms' });
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
            query = """SELECT date(start_date) as start_date, SUM(record_value) as record_value 
                       FROM health_data WHERE record_type = ? AND start_date >= ? 
                       GROUP BY date(start_date) ORDER BY start_date;"""
        elif aggregate == 'avg':
            query = """SELECT date(start_date) as start_date, AVG(record_value) as record_value 
                       FROM health_data WHERE record_type = ? AND start_date >= ? 
                       GROUP BY date(start_date) ORDER BY start_date;"""
        else:
            query = """SELECT start_date, record_value 
                       FROM health_data WHERE record_type = ? AND start_date >= ? 
                       ORDER BY start_date;"""
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

# --- MAIN EXECUTION ---

def print_usage():
    print("Usage: python health_dashboard_final.py [command]")
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
            print("---")
            print("[WARNING] 'waitress' is not installed. Falling back to the basic Flask server.")
            print("For better performance, please run: py -m pip install waitress")
            print("---")
            print("Starting web server on http://0.0.0.0:8080")
            app.run(host='0.0.0.0', port=8080, debug=False)
    else:
        print(f"Unknown command: {command}")
        print_usage()