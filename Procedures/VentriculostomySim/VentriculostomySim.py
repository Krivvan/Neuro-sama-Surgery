# -*- coding: utf-8 -*-
from __main__ import vtk, qt, ctk, slicer
import slicer # type: ignore (slicer will be available in 3D Slicer)

class VentriculostomySim:
    """Example procedure for ventriculostomy"""
    
    def __init__(self):
        self.name = "Ventriculostomy"
        self.description = "External ventricular drain placement procedure"
        self.websocketHandler = None
        
        # Define phases and their available actions
        self.currentPhase = "startup"
        self.phases = {
            "startup": {
                "name": "Startup",
                "description": "Procedure not yet started",
                "actions": []
            },
            # "preparation": {
            #     "name": "Preparation",
            #     "description": "We need to mark the entry point and make an incision",
            #     "actions": ["mark_entry_point", "confirm_position"]
            # },
            "cranial_access": {
                "name": "Cranial Access",
                "description": "We need to drill a burr hole for catheter access into the brain",
                "actions": ["drill_burr_hole", "inspect_hole"]
            },
            "catheter_placement": {
                "name": "Catheter Placement",
                "description": "Inserting the catheter",
                "actions": ["insert_catheter", "verify_placement", "secure_catheter"]
            },
            # "completion": {
            #     "name": "Completion",
            #     "description": "Final verification and closure",
            #     "actions": ["test_drainage", "close_wound"]
            # }
        }

    def createUI(self):
        """Create and return UI widgets for this procedure"""
        widgets = []
        
        # Description label
        print(f"Current phase: {self.currentPhase}")
        self.phaseLabel = qt.QLabel(self.phases[self.currentPhase]["name"])
        self.phaseDescriptionLabel = qt.QLabel(self.phases[self.currentPhase]["description"])
        self.phaseDescriptionLabel.setWordWrap(True)
        widgets.append(self.phaseLabel)
        widgets.append(self.phaseDescriptionLabel)

        self.nextPhaseButton = qt.QPushButton("Next Phase")
        self.nextPhaseButton.clicked.connect(self.onNextPhase)
        widgets.append(self.nextPhaseButton)

        return widgets
    
    def getNextPhase(self):
        """Get the next phase key in the sequence"""
        if not self.currentPhase:
            # If no current phase, return the first phase
            return list(self.phases.keys())[0] if self.phases else None
        
        phaseKeys = list(self.phases.keys())
        try:
            currentIndex = phaseKeys.index(self.currentPhase)
            # Check if there's a next phase
            if currentIndex + 1 < len(phaseKeys):
                return phaseKeys[currentIndex + 1]
            else:
                print("Already at the last phase")
                return None
        except ValueError:
            print(f"Current phase '{self.currentPhase}' not found in phases")
            return None
    
    def onNextPhase(self):
        """Handle the next phase button click"""
        nextPhase = self.getNextPhase()
        if nextPhase:
            self.setPhase(nextPhase)

    def setPhase(self, phaseKey):
        """Set the current phase and update available actions"""
        if phaseKey in self.phases:

            # Unregister actions based on current phase
            self.unregisterActions()

            self.currentPhase = phaseKey
            phase = self.phases[phaseKey]
            print(f"Phase changed to: {phase['name']} - {phase['description']}")

            # Register new actions based on phase
            self.registerActions()

            # Update labels
            self.phaseLabel.setText(self.phases[self.currentPhase]["name"])
            self.phaseDescriptionLabel.setText(self.phases[self.currentPhase]["description"])
        else:
            print(f"Invalid phase: {phaseKey}")
    
    def getAvailableActions(self):
        """Get list of actions available in the current phase"""
        if self.currentPhase and self.currentPhase in self.phases:
            return self.phases[self.currentPhase]["actions"]
        return []
    
    def registerActions(self):
        """Setup the procedure (register actions, etc.)"""

        # Phase cases
        actions = []
        if self.currentPhase == "cranial_access":
            actions = [
                {
                    "name": "move_drill",
                    "description": "Move the drill in a direction by a distance that can be specified in millimeters",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "distance": {"type": "number"},
                            "direction": {"type": "string", "enum": ["left", "right", "forward", "backward"]},
                        },
                        "required": ["distance", "direction"]
                    }
                },
                {
                    "name": "pivot_drill",
                    "description": "Pivot the drill by an angle that can be specified in degrees",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "angle": {"type": "number"},
                            "direction": {"type": "string", "enum": ["left", "right", "up", "down"]},
                        },
                        "required": ["angle", "direction"]
                    }
                },
            ]
        elif self.currentPhase == "catheter_placement":
            # Add actions for catheter_placement phase here
            actions = []
        
        self.websocketHandler.registerActions(actions)
    
    def unregisterActions(self):
        """Unregister actions based on current phase"""
        self.websocketHandler.unregisterActions(self.phases[self.currentPhase]["actions"])
        print(f"Unregistered {len(self.phases[self.currentPhase]['actions'])} actions for {self.currentPhase}")

    def onActionReceived(self, actionId, actionName, actionParams):
        """Handle an action received from Neuro"""
        print(f"VentriculostomySim received action: {actionName} (id: {actionId})")

        if self.currentPhase == "cranial_access":
            if actionName == "move_drill":
                #self.moveDrill(actionParams)
                return True, "Drill moved"
            elif actionName == "pivot_drill":
                #self.pivotDrill(actionParams)
                return True, "Drill pivoted"
            else:
                print(f"Unknown action: {actionName}")
                return False, "Unknown action"
        elif self.currentPhase == "catheter_placement":
            if actionName == "insert_catheter":
                #self.insertCatheter(actionParams)
                return True, "Catheter inserted"
            elif actionName == "verify_placement":
                #self.verifyPlacement(actionParams)
                return True, "Catheter placement verified"
            else:
                print(f"Unknown action: {actionName}")
                return False, "Unknown action"
        
        return False, "Error"
    

