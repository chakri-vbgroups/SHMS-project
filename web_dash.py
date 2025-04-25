import dash
from dash import dcc, html
import plotly.express as px
import pandas as pd
from pymongo import MongoClient
from dash.dependencies import Input, Output, State, ALL
import os
import websockets
import asyncio
import json
import threading

# MongoDB connection
mongo_client = MongoClient("mongodb://localhost:27017/")
mongo_collection = mongo_client["demo"]["machine_metrics"]

# Static image directory (assume images are stored in this folder)
IMAGE_FOLDER = "static/images"

# Dash App
app = dash.Dash(__name__, suppress_callback_exceptions=True)
app.title = "Smart Factory Dashboard"
app.config.suppress_callback_exceptions = True

app.layout = html.Div([
    dcc.Store(id='selected-machine', data='all'),

    html.H1("Factory Monitoring Dashboard", style={"textAlign": "center"}),

    dcc.Interval(id='interval-component', interval=10 * 1000, n_intervals=0),

    html.Div(id='graphs'),

    html.Hr(),

    html.Div(id='machine-buttons', style={
        "display": "flex", "flexWrap": "wrap", "justifyContent": "center", "gap": "10px", "marginTop": "20px"
    })
])

# WebSocket client callback
async def fetch_websocket_data():
    uri = "ws://localhost:8765"  # WebSocket server URI
    async with websockets.connect(uri) as websocket:
        while True:
            try:
                # Receive data (machine data and image path)
                message = await websocket.recv()
                data = json.loads(message)

                # Handle received data: update the machine data and image
                if "machine_id" in data:
                    machine_data = {
                        "machine_id": data['machine_id'],
                        "timestamp": data['timestamp'],
                        "temperature": data['temperature'],
                        "rpm": data['rpm']
                    }
                    image_src = data.get("image")

                    # Trigger an update in the Dash app using dcc.Store
                    app.layout = html.Div([
                        html.H1("Factory Monitoring Dashboard", style={"textAlign": "center"}),

                        dcc.Interval(id='interval-component', interval=10 * 1000, n_intervals=0),

                        html.Div([
                            html.H3(f"Machine: {machine_data['machine_id']}"),
                            html.P(f"Temperature: {machine_data['temperature']}°C"),
                            html.P(f"RPM: {machine_data['rpm']}"),
                        ]),

                        html.Div([
                            html.H4("Live Image:"),
                            html.Img(src=f"/{image_src}", style={"width": "80%", "height": "auto", "borderRadius": "8px", "boxShadow": "0 4px 8px rgba(0, 0, 0, 0.2)"})
                        ])
                    ])

            except Exception as e:
                print(f"Error in WebSocket communication: {e}")
                break

# Start WebSocket client in a separate thread
def start_websocket_client():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(fetch_websocket_data())

# Start WebSocket client in a background thread
threading.Thread(target=start_websocket_client, daemon=True).start()

# Update buttons
@app.callback(
    Output('machine-buttons', 'children'),
    Input('interval-component', 'n_intervals'),
    State('selected-machine', 'data')
)
def update_machine_buttons(n, selected):
    data = list(mongo_collection.find({}, {"_id": 0}).sort("timestamp", -1).limit(200))
    df = pd.DataFrame(data)

    if df.empty or 'machine_id' not in df.columns:
        return []

    # Filter machine_ids starting with 'M'
    machine_ids = sorted(mid for mid in df['machine_id'].unique() if mid.startswith('M'))

    buttons = [
        html.Button("Show All", id={'type': 'machine-button', 'index': 'all'},
                    style=_button_style('all', selected))
    ]

    for mid in machine_ids:
        buttons.append(html.Button(mid, id={'type': 'machine-button', 'index': mid},
                                   style=_button_style(mid, selected)))

    return buttons

# Update graphs and images based on selected machine
@app.callback(
    Output('graphs', 'children'),
    [Input('interval-component', 'n_intervals'),
     Input('selected-machine', 'data')]
)
def update_graphs(n, selected_machine):
    try:
        all_data = list(mongo_collection.find({}, {"_id": 0}).sort("timestamp", -1))
        df = pd.DataFrame(all_data)

        required_columns = {'timestamp', 'temperature', 'rpm', 'machine_id'}
        if df.empty or not required_columns.issubset(df.columns):
            return html.Div("No valid data available")

        # Filter only machine_ids that start with 'M'
        df = df[df['machine_id'].str.startswith('M')]

        if selected_machine is None:
            selected_machine = 'all'

        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
        df = df.dropna(subset=['timestamp'])
        df = df.sort_values(by="timestamp", ascending=True)

        now = df['timestamp'].max()
        recent_df = df[df['timestamp'] > now - pd.Timedelta(minutes=5)]

        if selected_machine == 'all':
            fig_temp = px.bar(recent_df, x="timestamp", y="temperature", color="machine_id",
                              title="Temperature Over Time")
            fig_rpm = px.bar(recent_df, x="machine_id", y="rpm", title="RPM", color="machine_id")

            return html.Div([dcc.Graph(figure=fig_temp), dcc.Graph(figure=fig_rpm)])
        else:
            machine_recent = recent_df[recent_df['machine_id'] == selected_machine]
            machine_full = df[df['machine_id'] == selected_machine]

            if machine_recent.empty:
                return html.Div("No recent data available for this machine.")

            fig_recent_temp = px.line(machine_recent, x="timestamp", y="temperature",
                                      title=f"{selected_machine} Recent Temperature")
            fig_recent_rpm = px.line(machine_recent, x="timestamp", y="rpm",
                                     title=f"{selected_machine} Recent RPM")

            fig_hist_temp = px.line(machine_full, x="timestamp", y="temperature",
                                    title=f"{selected_machine} Historical Temperature")
            fig_hist_rpm = px.line(machine_full, x="timestamp", y="rpm",
                                   title=f"{selected_machine} Historical RPM")

            # Fetch the latest image for the selected machine
            image_src = get_latest_image(selected_machine)

            return html.Div(style={"display": "flex", "flexDirection": "column", "gap": "20px"}, children=[
                # Left side: Present data (graphs)
                html.Div(style={"display": "flex", "gap": "20px", "alignItems": "center"}, children=[
                    html.Div(style={"flex": "1", "padding": "10px"}, children=[
                        dcc.Graph(figure=fig_recent_temp),
                        dcc.Graph(figure=fig_recent_rpm)
                    ]),
                    html.Div(style={"flex": "0.5", "padding": "10px", "textAlign": "center"}, children=[
                        # Image between graphs
                        html.Img(src=image_src, style={"width": "80%", "height": "auto", "borderRadius": "8px", "boxShadow": "0 4px 8px rgba(0, 0, 0, 0.2)"})
                    ])
                ]),

                # Bottom side: Historical data
                html.Div(style={"padding": "10px"}, children=[
                    dcc.Graph(figure=fig_hist_temp),
                    dcc.Graph(figure=fig_hist_rpm)
                ])
            ])
    except Exception as e:
        return html.Div(f"An error occurred: {str(e)}")

# Set machine when button is clicked
@app.callback(
    Output('selected-machine', 'data'),
    [Input({'type': 'machine-button', 'index': ALL}, 'n_clicks')],
    [State({'type': 'machine-button', 'index': ALL}, 'id'),
     State('selected-machine', 'data')],
    prevent_initial_call=True
)
def select_machine(n_clicks, ids, current_selected):
    triggered = dash.callback_context.triggered
    if not triggered or triggered[0]['value'] is None:
        return current_selected

    triggered_id = eval(triggered[0]['prop_id'].split('.')[0])
    return triggered_id['index']

# Function to get the latest image for a machine
def get_latest_image(machine_id):
    image_folder = IMAGE_FOLDER
    # Assuming images are named with the machine_id followed by timestamp
    machine_images = [img for img in os.listdir(image_folder) if img.startswith(machine_id)]
    if machine_images:
        latest_image = sorted(machine_images)[-1]
        return f"/static/images/{latest_image}"
    return "/static/images/default.png"

# Helper function to style buttons
def _button_style(machine_id, selected_machine):
    return {
        'backgroundColor': '#007bff' if machine_id == selected_machine else '#f8f9fa',
        'color': '#fff' if machine_id == selected_machine else '#000',
        'border': '1px solid #ddd',
        'padding': '10px 20px',
        'borderRadius': '5px',
        'cursor': 'pointer'
    }

if __name__ == '__main__':
    app.run(debug=True)
