# -*- coding: utf-8 -*-
from __main__ import vtk, qt, ctk, slicer
import slicer # type: ignore (slicer will be available in 3D Slicer)
from slicer.ScriptedLoadableModule import * # type: ignore

import os, sys
import numpy as np
import json
import threading

try:
    import websocket
except ImportError:
    print('Warning: websocket-client is not installed. Please install it: slicer.util.pip_install("websocket-client")')
    websocket = None


class NeuroWebSocketHandler(qt.QObject): # type: ignore
    """Handles WebSocket connection and Neuro API communication"""
    
    # Signals
    connected = qt.Signal()
    disconnected = qt.Signal()
    error = qt.Signal(str)
    messageReceived = qt.Signal(object)
    messageSent = qt.Signal(str, object)  # command, data
    actionReceived = qt.Signal(str, str, str)  # actionId, actionName, actionParams
    
    def __init__(self, gameName="Neurosama Surgery"):
        super().__init__()
        self.ws = None
        self.gameName = gameName
        self.wsThread = None
        self.isRunning = False
        self.url = None
    
    def connect(self, url):
        """Connect to the WebSocket server"""
        if websocket is None:
            self.error.emit("websocket-client is not installed")
            return
        
        self.url = url
        self.isRunning = True
        
        # Start WebSocket in a separate thread
        self.wsThread = threading.Thread(target=self._runWebSocket, daemon=True)
        self.wsThread.start()
    
    def disconnect(self):
        """Disconnect from the WebSocket server"""
        self.isRunning = False
        if self.ws:
            try:
                # Stop the run_forever loop
                self.ws.keep_running = False
                self.ws.close()
            except Exception as e:
                print(f"Error disconnecting WebSocket: {e}")
            self.ws = None
    
    def isConnected(self):
        """Check if WebSocket is connected"""
        return self.ws is not None and self.isRunning
    
    def _runWebSocket(self):
        """Run WebSocket in a separate thread"""
        try:
            self.ws = websocket.WebSocketApp(
                self.url,
                on_open=self._onOpen,
                on_message=self._onMessage,
                on_error=self._onError,
                on_close=self._onClose
            )
            
            # Run forever (blocking call)
            self.ws.run_forever()
            
        except Exception as e:
            print(f"WebSocket thread error: {e}")
            self.error.emit(str(e))
    
    def _onOpen(self, ws):
        """Called when WebSocket connection is established"""
        print("WebSocket connected")
        self.connected.emit()
        
        # Send startup message
        self.sendStartup()
    
    def _onClose(self, ws, close_status_code, close_msg):
        """Called when WebSocket connection is closed"""
        print("WebSocket disconnected")
        self.disconnected.emit()
    
    def _onError(self, ws, error):
        """Called when WebSocket encounters an error"""
        errorString = str(error)
        print(f"WebSocket error: {errorString}")
        self.error.emit(errorString)
    
    def _onMessage(self, ws, message):
        """Called when a message is received from the WebSocket"""
        try:
            data = json.loads(message)
            command = data.get("command")
            #print(f"Received message: {command}")
            
            self.messageReceived.emit(data)
            
            # Handle incoming messages based on command
            if command == "action":
                self._handleAction(data)
            else:
                print(f"Unknown command: {command}")
                
        except json.JSONDecodeError as e:
            print(f"Failed to parse WebSocket message: {e}")
    
    
    def _sendMessage(self, command, data=None):
        """Send a message to the WebSocket server"""
        """
        Parameters
        - `command`: The websocket command. 'startup', 'context', 'action/result', 'actions/register', 'actions/unregister', 'actions/force'
        - `game`: The game name. This is used to identify the game. It should _always_ be the same and should not change. You should use the game's display name, including any spaces and symbols (e.g. `"Buckshot Roulette"`). The server will not include this field.
        - `data`: The command data. This object is different depending on which command you are sending/receiving, and some commands may not have any data, in which case this object will be either `undefined` or `{}`.
        """
        if not self.isConnected():
            print("Cannot send message: WebSocket not connected")
            return
        
        message = {
            "command": command,
            "game": self.gameName
        }
        
        if data:
            message["data"] = data
        
        messageJson = json.dumps(message)
        
        try:
            self.ws.send(messageJson)
            print(f"Sent message: {command}")
            
            # Emit signal for logging
            self.messageSent.emit(command, data)
        except Exception as e:
            print(f"Failed to send message: {e}")
    
    def sendStartup(self):
        """Send startup message to Neuro API"""
        self._sendMessage("startup")
    
    def sendContext(self, message, silent=False):
        """Send context message to Neuro API"""
        self._sendMessage("context", {
            "message": message,
            "silent": silent
        })
    
    def sendActionResult(self, actionId, success, message=""):
        """Send action result to Neuro API"""
        resultData = {
            "id": actionId,
            "success": success,
            "message": message
        }
        
        self._sendMessage("action/result", resultData)
    
    def registerActions(self, actions):
        """Register actions with Neuro API"""
        self._sendMessage("actions/register", {
            "actions": actions
        })
    
    def unregisterActions(self, actionNames):
        """Unregister actions from Neuro API"""
        self._sendMessage("actions/unregister", {
            "action_names": actionNames
        })
    
    def forceActions(self, query, actionNames, state=None, ephemeralContext=False, priority="low"):
        """Force Neuro to execute one of the listed actions"""
        forceData = {
            "query": query,
            "action_names": actionNames,
            "ephemeral_context": ephemeralContext,
            "priority": priority
        }
        
        if state:
            forceData["state"] = state
        
        self._sendMessage("actions/force", forceData)
    
    def _handleAction(self, data):
        """Handle action message from Neuro"""
        actionData = data.get("data", {})
        actionId = actionData.get("id")
        actionName = actionData.get("name")
        actionParams = actionData.get("data")
        
        #print(f"Action received: {actionName} (id: {actionId})")
        self.actionReceived.emit(actionId, actionName, actionParams if actionParams else "")


class NeurosamaSurgery(ScriptedLoadableModule): # type: ignore
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent) # type: ignore
        parent.title = "Neuro-Sama Surgery"
        parent.categories = ["IGT"]
        parent.contributors = ["Krivvan (The Swarm)"]
        
        parent.helpText = """
        For use with the Neuro-Sama SDK: https://github.com/VedalAI/neuro-sdk
        """
        parent.acknowledgementText = """
        """ 
        # module build directory is not the current directory when running the python script
        self.parent = parent
        
        # Set module icon from Resources/Icons/<ModuleName>.png
        moduleDir = os.path.dirname(self.parent.path)
        for iconExtension in ['.svg', '.png']:
            iconPath = os.path.join(moduleDir, 'Resources/Icons', self.__class__.__name__ + iconExtension)
            if os.path.isfile(iconPath):
                parent.icon = qt.QIcon(iconPath)
                break

class NeurosamaSurgeryWidget(ScriptedLoadableModuleWidget): # type: ignore
    def __init__(self, parent = None):
        ScriptedLoadableModuleWidget.__init__(self, parent) # type: ignore
        if not parent:
            self.parent = slicer.qMRMLWidget()
            self.parent.setLayout(qt.QVBoxLayout())
            self.parent.setMRMLScene(slicer.mrmlScene)
        else:
            self.parent = parent
        self.layout = self.parent.layout()
        if not parent:
            self.setup()
            self.parent.show()
        self.moduleDir = os.path.dirname(os.path.abspath(__file__))

    def onReload(self, moduleName="NeurosamaSurgery"):
        # Clean up current procedure instance before reload
        if hasattr(self, 'currentProcedureInstance') and self.currentProcedureInstance:
            try:
                self.currentProcedureInstance.cleanup()
            except:
                pass
        
        # Clean up WebSocket handler before reload
        if hasattr(self, 'websocketHandler') and self.websocketHandler:
            self.websocketHandler.disconnect()
            self.websocketHandler.deleteLater()
            self.websocketHandler = None

        globals()[moduleName] = slicer.util.reloadScriptedModule(moduleName)
  
    def setup(self):
        ScriptedLoadableModuleWidget.setup(self) # type: ignore
        
        # =============================Initialization=============================
        # Initialize procedures dictionary and instances
        self.procedureClasses = {}
        self.currentProcedure = None
        self.currentProcedureInstance = None
        
        # Initialize WebSocket handler
        self.websocketHandler = NeuroWebSocketHandler("Neuro-Sama Surgery")
        self.websocketHandler.connected.connect(self.onWebSocketConnected)
        self.websocketHandler.disconnected.connect(self.onWebSocketDisconnected)
        self.websocketHandler.error.connect(self.onWebSocketError)
        self.websocketHandler.actionReceived.connect(self.onActionReceived)
        self.websocketHandler.messageReceived.connect(self.onMessageReceived)
        self.websocketHandler.messageSent.connect(self.logSentMessage)


        # Banner image
        
        bannerPath = os.path.join(self.moduleDir, "Resources", "Icons", "NeurosamaSurgeryBanner.png")
        
        bannerLabel = qt.QLabel()
        bannerPixmap = qt.QPixmap(bannerPath)
        # Scale the image if needed (optional)
        # bannerPixmap = bannerPixmap.scaledToWidth(400, qt.Qt.SmoothTransformation)
        bannerLabel.setPixmap(bannerPixmap)
        bannerLabel.setAlignment(qt.Qt.AlignCenter)
        self.layout.addWidget(bannerLabel)



        # Initialization UI
        initializationLayoutButton = ctk.ctkCollapsibleButton()
        initializationLayoutButton.text = "Initialization"
        self.layout.addWidget(initializationLayoutButton)
        initializationLayout = qt.QVBoxLayout(initializationLayoutButton)
        
        # WebSocket group
        websocketGroupBox = ctk.ctkCollapsibleGroupBox()
        websocketGroupBox.title = "Neuro Connection"
        initializationLayout.addWidget(websocketGroupBox)
        
        websocketLayout = qt.QFormLayout(websocketGroupBox)
        
        self.websocketUrlLineEdit = qt.QLineEdit()
        self.websocketUrlLineEdit.text = "ws://localhost:8000"
        self.websocketUrlLineEdit.toolTip = "Enter the WebSocket URL for the Neuro-Sama API"
        websocketLayout.addRow("WebSocket URL:", self.websocketUrlLineEdit)
        
        self.websocketConnectionButton = qt.QPushButton("Connect")
        self.websocketConnectionButton.toolTip = "Connect to or disconnect from the WebSocket server"
        self.websocketConnectionButton.checkable = True
        self.websocketConnectionButton.clicked.connect(self.onConnectionToggle)
        websocketLayout.addRow("Connection:", self.websocketConnectionButton)
        
        self.websocketConnectionStatusLabel = qt.QLabel("Disconnected")
        self.websocketConnectionStatusLabel.setStyleSheet("QLabel { color: gray; }")
        websocketLayout.addRow("Status:", self.websocketConnectionStatusLabel)

        # Procedure group
        procedureGroupBox = ctk.ctkCollapsibleGroupBox()
        procedureGroupBox.title = "Procedure Selection"
        initializationLayout.addWidget(procedureGroupBox)
        
        procedureLayout = qt.QFormLayout(procedureGroupBox)
        
        # Procedure combo box
        self.procedureComboBox = qt.QComboBox()
        self.procedureComboBox.toolTip = "Select a procedure"
        self.procedureComboBox.currentIndexChanged.connect(self.onProcedureChanged)
        procedureLayout.addRow("Procedure:", self.procedureComboBox)

        # Load and populate procedures
        self.loadProcedureList()
        
        # Load Procedure button
        self.loadProcedureButton = qt.QPushButton("Load Procedure")
        self.loadProcedureButton.toolTip = "Load the selected procedure (requires WebSocket connection)"
        self.loadProcedureButton.enabled = False
        self.loadProcedureButton.clicked.connect(self.onLoadProcedure)
        procedureLayout.addRow("", self.loadProcedureButton)
        
        # ===================================================================
        # ==========================Procedure UI=============================
        procedureUIButton = ctk.ctkCollapsibleButton()
        procedureUIButton.text = "Procedure"
        procedureUIButton.collapsed = True
        self.layout.addWidget(procedureUIButton)
        
        # This layout will be populated by the loaded procedure
        self.procedureUILayout = qt.QVBoxLayout(procedureUIButton)
        self.procedureUIGroupBox = procedureUIButton
        
        # ===================================================================
        # =============================Debug Log=============================
        # Log section
        logLayoutButton = ctk.ctkCollapsibleButton()
        logLayoutButton.text = "Debug Log"
        logLayoutButton.collapsed = True
        self.layout.addWidget(logLayoutButton)
        
        logLayout = qt.QVBoxLayout(logLayoutButton)
        
        # Horizontal layout for side-by-side message boxes
        logBoxesLayout = qt.QHBoxLayout()
        logLayout.addLayout(logBoxesLayout)
        
        # Sent messages box
        sentLayout = qt.QVBoxLayout()
        sentLabel = qt.QLabel("Sent to Neuro:")
        sentLabel.setStyleSheet("QLabel { font-weight: bold; }")
        sentLayout.addWidget(sentLabel)
        
        self.sentMessagesTextBox = qt.QPlainTextEdit()
        self.sentMessagesTextBox.readOnly = True
        self.sentMessagesTextBox.setMinimumHeight(200)
        sentLayout.addWidget(self.sentMessagesTextBox)
        
        logBoxesLayout.addLayout(sentLayout)
        
        # Received messages box
        receivedLayout = qt.QVBoxLayout()
        receivedLabel = qt.QLabel("Received from Neuro:")
        receivedLabel.setStyleSheet("QLabel { font-weight: bold; }")
        receivedLayout.addWidget(receivedLabel)
        
        self.receivedMessagesTextBox = qt.QPlainTextEdit()
        self.receivedMessagesTextBox.readOnly = True
        self.receivedMessagesTextBox.setMinimumHeight(200)
        receivedLayout.addWidget(self.receivedMessagesTextBox)
        
        logBoxesLayout.addLayout(receivedLayout)
        
        # Clear log button
        clearLogButton = qt.QPushButton("Clear Log")
        clearLogButton.clicked.connect(self.onClearLog)
        logLayout.addWidget(clearLogButton)
        # ===================================================================
        
        self.layout.addStretch(1)
    
    def loadProcedureList(self):
        """Load procedure classes from subfolders in the Procedures folder"""
        print("Populating procedure list")
        self.procedureClasses = {}
        
        # Get the module directory
        proceduresDir = os.path.join(self.moduleDir, "Procedures")
        
        if not os.path.exists(proceduresDir):
            print(f"Procedures directory not found: {proceduresDir}")
            return
        
        # Find all subdirectories in Procedures folder
        for item in os.listdir(proceduresDir):
            itemPath = os.path.join(proceduresDir, item)
            
            # Only process directories (skip files)
            if os.path.isdir(itemPath) and not item.startswith("__"):
                procedureName = item
            
            #try:
                # Add the specific procedure directory to path
                if itemPath not in sys.path:
                    sys.path.insert(0, itemPath)
                
                # Try to import the module with the same name as the folder
                module = __import__(procedureName)
                
                # Look for a class with the same name as the folder
                if hasattr(module, procedureName):
                    procedureClass = getattr(module, procedureName)
                    
                    # Store the procedure class (not an instance)
                    self.procedureClasses[procedureName] = procedureClass
                    
                    # Add to combo box using folder name as display name
                    self.procedureComboBox.addItem(procedureName)
                    
                    print(f"Loaded procedure class: {procedureName}")
                else:
                    print(f"Class '{procedureName}' not found in module '{procedureName}'")
                    
                # except Exception as e:
                #     print(f"Failed to load procedure {procedureName}: {e}")
        
    def onProcedureChanged(self, index):
        """Called when the procedure selection changes"""
        if index < 0:
            self.currentProcedure = None
            return
        
        procedureName = self.procedureComboBox.currentText
        self.currentProcedure = procedureName
        
        if self.currentProcedure:
            print(f"Selected procedure: {self.currentProcedure}")
    
    def onLoadProcedure(self):
        """Load the selected procedure and populate its UI"""
        if not self.currentProcedure:
            print("No procedure selected")
            return
        
        if not self.websocketHandler.isConnected():
            print("Cannot load procedure: WebSocket not connected")
            return
        
        # Get the procedure class
        procedureClass = self.procedureClasses.get(self.currentProcedure)
        if not procedureClass:
            print(f"Procedure class not found: {self.currentProcedure}")
            return
        
        print(f"Loading procedure: {self.currentProcedure}")
        
        # Cleanup previous procedure instance if it exists
        if self.currentProcedureInstance:
            try:
                self.currentProcedureInstance.cleanup()
            except Exception as e:
                print(f"Error cleaning up previous procedure: {e}")
        
        # Instantiate the procedure class
        try:
            self.currentProcedureInstance = procedureClass()
            self.currentProcedureInstance.websocketHandler = self.websocketHandler
        except Exception as e:
            print(f"Error instantiating procedure: {e}")
            return
        
        # Clear existing procedure UI
        self.clearProcedureUI()
        
        # Get UI widgets from the procedure and add to layout
        if hasattr(self.currentProcedureInstance, 'createUI'):
            procedureWidgets = self.currentProcedureInstance.createUI()
            if procedureWidgets:
                for widget in procedureWidgets:
                    self.procedureUILayout.addWidget(widget)

        
        # Expand the procedure UI group box
        self.procedureUIGroupBox.collapsed = False
        self.procedureUIGroupBox.text = f"Procedure: {self.currentProcedureInstance.__class__.__name__}"

        # Load the MRML scene for the procedure
        self.loadProcedureScene()
        
    
    def clearProcedureUI(self):
        """Clear all widgets from the procedure UI layout"""
        while self.procedureUILayout.count():
            item = self.procedureUILayout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
    
    def loadProcedureScene(self):
        """Load the MRML scene bundle from the procedure's scene folder"""
        if not self.currentProcedure:
            print("No procedure selected")
            return
        
        # Get the module directory and procedure scene directory
        procedureDir = os.path.join(self.moduleDir, "Procedures", self.currentProcedure)
        sceneDir = os.path.join(procedureDir, "scene")
        
        if not os.path.exists(sceneDir):
            print(f"Scene directory not found: {sceneDir}")
            return
        
        mrbFiles = [f for f in os.listdir(sceneDir) if f.endswith('.mrb')]
        
        if not mrbFiles:
            print(f"No .mrb files found in: {sceneDir}")
            return
        
        # Load the first .mrb file found
        mrbPath = os.path.join(sceneDir, mrbFiles[0])
        
        try:
            print(f"Loading scene bundle: {mrbPath}")
            # Clear the current scene first
            slicer.mrmlScene.Clear(0)
            # Load the scene bundle
            slicer.util.loadScene(mrbPath)
            print(f"Scene bundle loaded successfully: {mrbFiles[0]}")
        except Exception as e:
            print(f"Error loading scene bundle: {e}")
    
    def onConnectionToggle(self, checked):
        """Handle WebSocket connection toggle"""
        if checked:
            url = self.websocketUrlLineEdit.text
            self.websocketConnectionButton.text = "Disconnect"
            self.websocketConnectionStatusLabel.text = "Connecting..."
            self.websocketConnectionStatusLabel.setStyleSheet("QLabel { color: orange; }")
            self.websocketUrlLineEdit.enabled = False
            
            self.websocketHandler.connect(url)
        else:
            self.websocketHandler.disconnect()
    
    def onWebSocketConnected(self):
        self.websocketConnectionStatusLabel.text = "Connected"
        self.websocketConnectionStatusLabel.setStyleSheet("QLabel { color: green; }")
        
        # Enable procedure loading when connected
        self.loadProcedureButton.enabled = True
    
    def onWebSocketDisconnected(self):
        self.websocketConnectionStatusLabel.text = "Disconnected"
        self.websocketConnectionStatusLabel.setStyleSheet("QLabel { color: gray; }")
        self.websocketConnectionButton.checked = False
        self.websocketConnectionButton.text = "Connect"
        self.websocketUrlLineEdit.enabled = True
        
        # Disable procedure loading when disconnected
        self.loadProcedureButton.enabled = False
    
    def onWebSocketError(self, errorString):
        """Called when WebSocket encounters an error"""
        self.websocketConnectionStatusLabel.text = f"Error: {errorString}"
        self.websocketConnectionStatusLabel.setStyleSheet("QLabel { color: red; }")
    
    def onActionReceived(self, actionId, actionName, actionParams):
        """Called when an action is received from Neuro"""
        print(f"Widget received action: {actionName} (id: {actionId})")
        
        if self.currentProcedureInstance:
           actionResult, message = self.currentProcedureInstance.onActionReceived(actionId, actionName, actionParams)
        else:
            print("No procedure instance found")
        self.websocketHandler.sendActionResult(actionId, actionResult, message)
    
    def onMessageReceived(self, data):
        """Called when a message is received from Neuro"""
        messageJson = json.dumps(data, indent=2)
        timestamp = qt.QDateTime.currentDateTime().toString("hh:mm:ss")
        logEntry = f"[{timestamp}]\n{messageJson}\n\n"
        self.receivedMessagesTextBox.appendPlainText(logEntry)
    
    def logSentMessage(self, command, data=None):
        """Log a message sent to Neuro"""
        message = {
            "command": command,
            "game": self.websocketHandler.gameName
        }
        if data:
            message["data"] = data
        
        messageJson = json.dumps(message, indent=2)
        timestamp = qt.QDateTime.currentDateTime().toString("hh:mm:ss")
        logEntry = f"[{timestamp}]\n{messageJson}\n\n"
        self.sentMessagesTextBox.appendPlainText(logEntry)
    
    def onClearLog(self):
        """Clear both message log boxes"""
        self.sentMessagesTextBox.clear()
        self.receivedMessagesTextBox.clear()
