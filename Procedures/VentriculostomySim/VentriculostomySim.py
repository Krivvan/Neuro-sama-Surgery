# -*- coding: utf-8 -*-
from __main__ import vtk, qt, ctk, slicer
import slicer # type: ignore (slicer will be available in 3D Slicer)
import json

class VentriculostomySim:
    """Example procedure for ventriculostomy"""
    
    def __init__(self):
        self.name = "Ventriculostomy"
        self.description = "External ventricular drain placement procedure"
        self.websocketHandler = None
        self.moving = False

        self.selectedVentriclePosition = None
        
        # Movement animation variables
        self.movementTimer = None
        self.movementStartTime = None
        self.movementTotalDistance = 0.0
        self.movementSpeed = 20.0  # mm per second
        self.currentPathCurve = None
        self.startOrientation = None  # Starting orientation quaternion
        self.targetOrientation = None  # Target orientation quaternion
        
        # Catheter movement animation variables
        self.catheterTimer = None
        self.catheterStartTime = None
        self.catheterTotalDistance = 0.0
        self.catheterSpeed = 10.0  # mm per second
        self.catheterDirection = [0.0, 0.0, 0.0]  # Direction vector for catheter movement
        self.catheterStartPosition = [0.0, 0.0, 0.0]  # Starting position
        self.catheterMovementType = ""  # "insert" or "retract"
        
        # Define phases and their available actions
        self.currentPhase = "startup"
        self.phases = {
            "startup": {
                "name": "Startup",
                "description": "The procedure has not yet started",
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
                "actions": ["move_to_drill_site", "drill_hole"]
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
            print(f"Current phase: {self.currentPhase}")

             # Phase-specific scene/UI changes
            if self.currentPhase == "cranial_access":
                # Show green slice and set opacity to 0.5
                greenNode = slicer.util.getNode("Green Volume Slice")
                greenSliceNode = slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeGreen")
                if greenSliceNode and greenNode:
                    greenSliceNode.SetSliceEdgeVisibility3D(False)
                    greenSliceNode.SetSliceVisible(True)
                    greenNode.GetDisplayNode().SetOpacity(1.0)
                yellowSliceNode = slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeYellow")
                if yellowSliceNode:
                    yellowSliceNode.SetSliceVisible(False)
            elif self.currentPhase == "catheter_placement":
                # Show yellow slice and set opacity to 0.5
                greenSliceNode = slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeGreen")
                if greenSliceNode:
                    greenSliceNode.SetSliceVisible(False)
                yellowNode = slicer.util.getNode("Yellow Volume Slice")
                yellowSliceNode = slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeYellow")
                if yellowNode and yellowSliceNode:
                    yellowSliceNode.SetSliceEdgeVisibility3D(False)
                    yellowSliceNode.SetSliceVisible(True)
                    yellowNode.GetDisplayNode().SetOpacity(1.0)

                # Hide trajectory model
                trajectoryModelNode = slicer.util.getFirstNodeByName("TrajectoryModel")
                if trajectoryModelNode:
                    # Hide the trajectory model
                    trajectoryDisplayNode = trajectoryModelNode.GetDisplayNode()
                    if trajectoryDisplayNode:
                        trajectoryDisplayNode.SetVisibility(False)

            # Register new actions based on phase
            self.registerActions()

            # Update labels
            self.phaseLabel.setText(self.phases[self.currentPhase]["name"])
            self.phaseDescriptionLabel.setText(self.phases[self.currentPhase]["description"])
        else:
            print(f"Invalid phase: {phaseKey}") 
    
    def registerActions(self):
        """Setup the procedure (register actions, etc.) for the current phase"""
        # TODO: I may need to rethink this if the actions need to be more micromanaged. Or maybe just reporting errors back is fine

        # Phase cases
        actions = []
        if self.currentPhase == "cranial_access":
            actions = [
                {
                    "name": "move_to_drill_site",
                    "description": "Move the drill to a location on the head.",
                    "schema": {                        
                        "type": "object",
                        "properties": {
                            "location": {"type": "string", "enum": ["kochers_point_left", "kochers_point_right", "glabella", "nasion", "pterion_left", "pterion_right", "bregma", "maccartys_keyhole_left", "maccartys_keyhole_right", "keens_point_left", "keens_point_right"]},
                        },
                        "required": ["location"]
                    }
                },
                # {
                #     "name": "make_incision",
                #     "description": "Make an incision on the head to prepare to start drilling.",
                #     "schema": {
                #     }
                # },
                {
                    "name": "drill_hole",
                    "description": "Start drilling into the skull. Doing this will move you to the next phase of the procedure.",
                    "schema": {
                    }
                },                
            ]
        elif self.currentPhase == "catheter_placement":
            # Add actions for catheter_placement phase here
            actions = [
                {
                    "name": "insert_catheter",
                    "description": "Insert the catheter by some distance. We want the catheter to reach the ventricles to drain them. Distance should be in mm.",
                    "schema": {                       
                        "type": "object",
                        "properties": {
                            "distance": {"type": "number", "minimum": 1, "maximum": 100},
                        },
                        "required": ["distance"]
                    }
                },
                {
                    "name": "retract_catheter",
                    "description": "Retract the catheter by some distance. We want the catheter to reach the ventricles to drain them. Distance should be in mm.",
                    "schema": {                       
                        "type": "object",
                        "properties": {
                            "distance": {"type": "number", "minimum": 1, "maximum": 100},
                        },
                        "required": ["distance"]
                    }
                },
                {
                    "name": "start_draining",
                    "description": "Start draining the ventricles of fluid.",
                    "schema": {
                    }
                },
            ]   
        
        self.websocketHandler.registerActions(actions)
    
    def unregisterActions(self):
        """Unregister actions based on current phase"""
        self.websocketHandler.unregisterActions(self.phases[self.currentPhase]["actions"])
        print(f"Unregistered {len(self.phases[self.currentPhase]['actions'])} actions for {self.currentPhase}")

    def onActionReceived(self, actionId, actionName, actionParams):
        """Handle an action received from Neuro"""
        print(f"VentriculostomySim received action: {actionName} (id: {actionId})")

        if self.moving:
            return False, "We are currently moving the tool. Please wait until we finish moving before performing any actions."

        if self.currentPhase == "cranial_access":
            if actionName == "move_to_drill_site":
                actionResult, resultMessage = self.cranial_move_to_drill_site(actionParams)
                return actionResult, resultMessage
            elif actionName == "make_incision":
                actionResult, resultMessage = self.cranial_make_incision(actionParams)
                return actionResult, resultMessage
            elif actionName == "drill_hole":
                actionResult, resultMessage = self.cranial_drill_hole(actionParams)
                return actionResult, resultMessage    
            else:
                print(f"Unknown action: {actionName}")
                return False, f"Unknown action. {actionName} is not an available action that can be performed."
        elif self.currentPhase == "catheter_placement":
            if actionName == "insert_catheter":
                actionResult, resultMessage = self.catheter_insert_catheter(actionParams)
                return actionResult, resultMessage
            elif actionName == "retract_catheter":
                actionResult, resultMessage = self.catheter_retract_catheter(actionParams)
                return actionResult, resultMessage
            elif actionName == "start_draining":
                actionResult, resultMessage = self.catheter_drain(actionParams)
                return actionResult, resultMessage    
            else:
                print(f"Unknown action: {actionName}")
                return False, f"Unknown action. {actionName} is not an available action that can be performed."
        
        return False, "Error"

    # ================================Cranial Access Functions===================================
    def cranial_move_to_drill_site(self, actionParams):
        drillSitesFiducialNode = slicer.util.getFirstNodeByName("DrillSiteFiducials")
        drillSiteFound = False
        drillSitePosition = [0.0, 0.0, 0.0]
        
        # Parse actionParams - it comes as a JSON string
        if isinstance(actionParams, str) and actionParams:
            try:
                actionParams = json.loads(actionParams)
            except json.JSONDecodeError:
                return False, "Doctor, I couldn't understand the location parameters"
        
        # Now extract the location
        if isinstance(actionParams, dict):
            requestedLocation = actionParams["location"]
        else:
            requestedLocation = ""

        print(f"Requested location: {requestedLocation}")
        
        for drillSiteFiducialIndex in range(drillSitesFiducialNode.GetNumberOfControlPoints()):
            fiducialLabel = drillSitesFiducialNode.GetNthControlPointLabel(drillSiteFiducialIndex)
            if fiducialLabel == requestedLocation:
                drillSitesFiducialNode.GetNthControlPointPosition(drillSiteFiducialIndex, drillSitePosition)
                drillSiteFound = True
                break
        
        if not drillSiteFound:
            return False, "Doctor, I don't know what that drill site location is"

        # Now that the drill site position is found, change IntendedToolTransform's position
        intendedToolTransformNode = slicer.util.getFirstNodeByName("IntendedToolTransform")
        transformMatrix = vtk.vtkMatrix4x4()
        intendedToolTransformNode.GetMatrixTransformToParent(transformMatrix)
        transformMatrix.SetElement(0, 3, drillSitePosition[0])
        transformMatrix.SetElement(1, 3, drillSitePosition[1])
        transformMatrix.SetElement(2, 3, drillSitePosition[2])
        intendedToolTransformNode.SetMatrixTransformToParent(transformMatrix)

        # Now, we need to set IntendedToolTransform's orientation. This will be to the closest ventricle fiducial location
        closestVentriclePosition, closestVentricleIndex = self.find_closest_ventricle_fiducial(drillSitePosition)
        
        if closestVentriclePosition is None:
            return False, "Doctor, I can't find any ventricle fiducials to aim towards"

        self.selectedVentriclePosition = closestVentriclePosition

        # Calculate the vector to it from IntendedToolTransform's position, then set the orientation of it towards it
        directionVector = [
            closestVentriclePosition[0] - drillSitePosition[0],
            closestVentriclePosition[1] - drillSitePosition[1],
            closestVentriclePosition[2] - drillSitePosition[2]
        ]
        
        # Normalize the direction vector
        magnitude = (directionVector[0]**2 + directionVector[1]**2 + directionVector[2]**2)**0.5
        if magnitude > 0:
            directionVector = [d / magnitude for d in directionVector]
        
        # Create a rotation matrix that points the Z-axis towards the ventricle
        # Use the direction as the Z-axis (forward direction)
        zAxis = directionVector
        
        # Create an arbitrary perpendicular vector for X-axis
        # Choose a vector that's not parallel to Z
        if abs(zAxis[0]) < 0.9:
            arbitrary = [1.0, 0.0, 0.0]
        else:
            arbitrary = [0.0, 1.0, 0.0]
        
        # X-axis = arbitrary cross Z-axis (normalized)
        xAxis = [
            arbitrary[1] * zAxis[2] - arbitrary[2] * zAxis[1],
            arbitrary[2] * zAxis[0] - arbitrary[0] * zAxis[2],
            arbitrary[0] * zAxis[1] - arbitrary[1] * zAxis[0]
        ]
        xMagnitude = (xAxis[0]**2 + xAxis[1]**2 + xAxis[2]**2)**0.5
        xAxis = [x / xMagnitude for x in xAxis]
        
        # Y-axis = Z-axis cross X-axis
        yAxis = [
            zAxis[1] * xAxis[2] - zAxis[2] * xAxis[1],
            zAxis[2] * xAxis[0] - zAxis[0] * xAxis[2],
            zAxis[0] * xAxis[1] - zAxis[1] * xAxis[0]
        ]
        
        # Set the rotation part of the transform matrix (columns 0-2, rows 0-2)
        transformMatrix.SetElement(0, 0, xAxis[0])
        transformMatrix.SetElement(1, 0, xAxis[1])
        transformMatrix.SetElement(2, 0, xAxis[2])
        
        transformMatrix.SetElement(0, 1, yAxis[0])
        transformMatrix.SetElement(1, 1, yAxis[1])
        transformMatrix.SetElement(2, 1, yAxis[2])
        
        transformMatrix.SetElement(0, 2, zAxis[0])
        transformMatrix.SetElement(1, 2, zAxis[1])
        transformMatrix.SetElement(2, 2, zAxis[2])
        
        # Apply the updated matrix to the transform node
        intendedToolTransformNode.SetMatrixTransformToParent(transformMatrix)
        
        # Change the length of the trajectory model to match the distance to the ventricle fiducial
        trajectoryModelNode = slicer.util.getFirstNodeByName("TrajectoryModel")
        if trajectoryModelNode:
            # Hide the trajectory model
            trajectoryDisplayNode = trajectoryModelNode.GetDisplayNode()
            if trajectoryDisplayNode:
                trajectoryDisplayNode.SetVisibility(False)
            
            # Create a cylinder with the correct length (height = distance to ventricle)
            cylinderSource = vtk.vtkCylinderSource()
            cylinderSource.SetHeight(magnitude)
            cylinderSource.SetRadius(3.0)  # 1mm radius for visibility
            cylinderSource.SetResolution(20)
            cylinderSource.Update()
            
            # The cylinder is created along Y-axis by default, we need it along Z-axis
            # Create a transform to rotate it 90 degrees around X to align with Z
            # Then translate it so the origin is at one end (the base)
            transform = vtk.vtkTransform()
            transform.Translate(0, 0, magnitude / 2.0)  # Move origin to the base of the cylinder
            transform.RotateX(90)
            
            transformFilter = vtk.vtkTransformPolyDataFilter()
            transformFilter.SetInputConnection(cylinderSource.GetOutputPort())
            transformFilter.SetTransform(transform)
            transformFilter.Update()
            
            # Set the new polydata on the trajectory model
            trajectoryModelNode.SetAndObservePolyData(transformFilter.GetOutput())

        # Create a path from the current location to the intended location
        pathCurve = self.generate_safety_path()
        
        # Initiate the movement towards it
        if pathCurve:
            # Set skull model to have opacity 1.0
            skullModelNode = slicer.util.getFirstNodeByName("SkullModel")
            if skullModelNode:
                skullDisplayNode = skullModelNode.GetDisplayNode()
                if skullDisplayNode:
                    skullDisplayNode.SetOpacity(1.00)
            self.start_path_movement(pathCurve)
        else:
            return False, "Doctor, I couldn't generate a safe path to that location"

        # This is enough for the action for now, we need to send the result back to Neuro
        return True, "We are moving towards your chosen potential drill site. You will need to wait until we reach it."

    def check_drill_site(self):
        """This is called after arriving at a potential drill site. We see if we will hit any blood vessels"""
        # Set skull model to have opacity 0.5
        skullModelNode = slicer.util.getFirstNodeByName("SkullModel")
        if skullModelNode:
            skullDisplayNode = skullModelNode.GetDisplayNode()
            if skullDisplayNode:
                skullDisplayNode.SetOpacity(0.1)
        
        trajectoryModelNode = slicer.util.getFirstNodeByName("TrajectoryModel")
        vesselsModelNode = slicer.util.getFirstNodeByName("VesselsModel")

        # See if the trajectory model intersects with any polys from the Vessel model
        trajectoryPolyData = trajectoryModelNode.GetPolyData()
        vesselsPolyData = vesselsModelNode.GetPolyData()
        
        # Use VTK collision detection filter
        collisionDetection = vtk.vtkCollisionDetectionFilter()
        collisionDetection.SetInputData(0, trajectoryPolyData)
        collisionDetection.SetInputData(1, vesselsPolyData)
        
        # Get the world transform matrices for both models
        trajectoryMatrix = vtk.vtkMatrix4x4()
        trajectoryParentTransform = trajectoryModelNode.GetParentTransformNode()
        if trajectoryParentTransform:
            trajectoryParentTransform.GetMatrixTransformToWorld(trajectoryMatrix)
        # else trajectoryMatrix remains as identity
        
        vesselsMatrix = vtk.vtkMatrix4x4()
        vesselsParentTransform = vesselsModelNode.GetParentTransformNode()
        if vesselsParentTransform:
            vesselsParentTransform.GetMatrixTransformToWorld(vesselsMatrix)
        # else vesselsMatrix remains as identity
        
        collisionDetection.SetMatrix(0, trajectoryMatrix)
        collisionDetection.SetMatrix(1, vesselsMatrix)
        
        collisionDetection.SetBoxTolerance(0.0)
        collisionDetection.SetCellTolerance(0.0)
        collisionDetection.SetNumberOfCellsPerNode(2)
        collisionDetection.Update()
        
        intersects = collisionDetection.GetNumberOfContacts() > 0

        # Show the trajectory model
        trajectoryDisplayNode = trajectoryModelNode.GetDisplayNode()
        if trajectoryDisplayNode:
            trajectoryDisplayNode.SetVisibility(True)

        # Color trajectory red if it will intersect and green if it is safe. Also construct the reportMessage
        trajectoryDisplayNode = trajectoryModelNode.GetDisplayNode()
        if intersects:
            # Red color for intersection
            trajectoryDisplayNode.SetColor(1.0, 0.0, 0.0)
            reportMessage = "Doctor, we have finished moving but we will intersect with a blood vessel if we proceed. Please move to a different location."
        else:
            # Green color for safe trajectory
            trajectoryDisplayNode.SetColor(0.0, 1.0, 0.0)
            reportMessage = "Doctor, we have finished moving and we will not intersect with a blood vessel if we proceed. You can now proceed with drilling."
        
        # Send a context message back reporting if the trajectory is good and informing that we can proceed with the next action of making an incision (maybe I should register/unregister for this instead)
        self.websocketHandler.sendContext(reportMessage, False)

    def find_closest_ventricle_fiducial(self, drillSitePosition):
        """Find the closest ventricle fiducial to the given position.
        
        Args:
            drillSitePosition: [x, y, z] position to compare against
            
        Returns:
            Tuple of (closestPosition, closestIndex) or (None, -1) if no fiducials found
        """
        ventricleFiducialNode = slicer.util.getFirstNodeByName("VentricleFiducials")
        
        if not ventricleFiducialNode or ventricleFiducialNode.GetNumberOfControlPoints() == 0:
            return None, -1
        
        closestDistance = float('inf')
        closestIndex = -1
        closestPosition = [0.0, 0.0, 0.0]
        
        for fiducialIndex in range(ventricleFiducialNode.GetNumberOfControlPoints()):
            currentPosition = [0.0, 0.0, 0.0]
            ventricleFiducialNode.GetNthControlPointPosition(fiducialIndex, currentPosition)
            
            # Calculate Euclidean distance
            distance = ((currentPosition[0] - drillSitePosition[0]) ** 2 +
                       (currentPosition[1] - drillSitePosition[1]) ** 2 +
                       (currentPosition[2] - drillSitePosition[2]) ** 2) ** 0.5
            
            if distance < closestDistance:
                closestDistance = distance
                closestIndex = fiducialIndex
                closestPosition = currentPosition.copy()
        
        return closestPosition, closestIndex

    def generate_safety_path(self):
        """Generate a path from ToolTransform to IntendedToolTransform that avoids SafetyZoneModel.
        
        The path consists of three segments:
        1. Retract: Move straight away from skull until outside the safety zone
        2. Arc: Move around the safety zone to get close to the target
        3. Approach: Move forward to the intended position
        
        Returns:
            vtkMRMLMarkupsCurveNode containing the path waypoints, or None if path cannot be generated
        """
        import math
        
        # Get the required nodes
        toolTransformNode = slicer.util.getFirstNodeByName("ToolTransform")
        intendedToolTransformNode = slicer.util.getFirstNodeByName("IntendedToolTransform")
        safetyZoneModelNode = slicer.util.getFirstNodeByName("SafetyZoneModel")
        skullModelNode = slicer.util.getFirstNodeByName("SkullModel")
        
        if not all([toolTransformNode, intendedToolTransformNode, safetyZoneModelNode, skullModelNode]):
            print("Error: Could not find all required nodes for path generation")
            return None
        
        # Get current tool position
        toolMatrix = vtk.vtkMatrix4x4()
        toolTransformNode.GetMatrixTransformToParent(toolMatrix)
        currentPos = [
            toolMatrix.GetElement(0, 3),
            toolMatrix.GetElement(1, 3),
            toolMatrix.GetElement(2, 3)
        ]
        
        # Get intended tool position
        intendedMatrix = vtk.vtkMatrix4x4()
        intendedToolTransformNode.GetMatrixTransformToParent(intendedMatrix)
        targetPos = [
            intendedMatrix.GetElement(0, 3),
            intendedMatrix.GetElement(1, 3),
            intendedMatrix.GetElement(2, 3)
        ]
        
        # Get safety zone sphere center and radius
        safetyZonePolyData = safetyZoneModelNode.GetPolyData()
        safetyZoneBounds = [0, 0, 0, 0, 0, 0]
        safetyZonePolyData.GetBounds(safetyZoneBounds)
        
        safetyZoneCenter = [
            (safetyZoneBounds[0] + safetyZoneBounds[1]) / 2.0,
            (safetyZoneBounds[2] + safetyZoneBounds[3]) / 2.0,
            (safetyZoneBounds[4] + safetyZoneBounds[5]) / 2.0
        ]
        
        safetyZoneRadius = max(
            (safetyZoneBounds[1] - safetyZoneBounds[0]) / 2.0,
            (safetyZoneBounds[3] - safetyZoneBounds[2]) / 2.0,
            (safetyZoneBounds[5] - safetyZoneBounds[4]) / 2.0
        )
        
        # Add a small buffer to the radius for safety
        safetyBuffer = 5.0  # mm
        safetyZoneRadius += safetyBuffer
        
        # Get skull center (approximated from bounds)
        skullPolyData = skullModelNode.GetPolyData()
        skullBounds = [0, 0, 0, 0, 0, 0]
        skullPolyData.GetBounds(skullBounds)
        
        skullCenter = [
            (skullBounds[0] + skullBounds[1]) / 2.0,
            (skullBounds[2] + skullBounds[3]) / 2.0,
            (skullBounds[4] + skullBounds[5]) / 2.0
        ]
        
        # Helper function to calculate distance between two points
        def distance(p1, p2):
            return math.sqrt(sum((a - b) ** 2 for a, b in zip(p1, p2)))
        
        # Helper function to normalize a vector
        def normalize(v):
            mag = math.sqrt(sum(x ** 2 for x in v))
            return [x / mag for x in v] if mag > 0 else [0, 0, 0]
        
        # Helper function to add two vectors
        def add_vectors(v1, v2):
            return [a + b for a, b in zip(v1, v2)]
        
        # Helper function to scale a vector
        def scale_vector(v, scale):
            return [x * scale for x in v]
        
        waypoints = []
        
        # SEGMENT 1: Retract away from skull if currently inside safety zone
        distFromSafetyZone = distance(currentPos, safetyZoneCenter)
        
        if distFromSafetyZone < safetyZoneRadius:
            # Calculate direction away from skull (from skull center to current position)
            retractDirection = normalize([
                currentPos[0] - skullCenter[0],
                currentPos[1] - skullCenter[1],
                currentPos[2] - skullCenter[2]
            ])
            
            # Calculate how far we need to move to get outside the safety zone
            # We want to be at safetyZoneRadius distance from safetyZoneCenter
            # Move along retractDirection until we're outside
            retractDistance = safetyZoneRadius - distFromSafetyZone + 10.0  # +10mm extra clearance
            
            retractPos = add_vectors(currentPos, scale_vector(retractDirection, retractDistance))
            waypoints.append(retractPos)
            startPos = retractPos
        else:
            startPos = currentPos
        
        # SEGMENT 2: Arc around the safety zone
        # Calculate if a straight line from startPos to targetPos intersects the safety zone
        dirToTarget = [
            targetPos[0] - startPos[0],
            targetPos[1] - startPos[1],
            targetPos[2] - startPos[2]
        ]
        distToTarget = math.sqrt(sum(x ** 2 for x in dirToTarget))
        
        if distToTarget > 0:
            dirToTargetNorm = normalize(dirToTarget)
            
            # Find the closest point on the line from startPos to targetPos to the safety zone center
            # Using vector projection
            vecToCenter = [
                safetyZoneCenter[0] - startPos[0],
                safetyZoneCenter[1] - startPos[1],
                safetyZoneCenter[2] - startPos[2]
            ]
            
            projectionLength = sum(a * b for a, b in zip(vecToCenter, dirToTargetNorm))
            projectionLength = max(0, min(projectionLength, distToTarget))  # Clamp to line segment
            
            closestPointOnLine = add_vectors(startPos, scale_vector(dirToTargetNorm, projectionLength))
            distFromLineToCenter = distance(closestPointOnLine, safetyZoneCenter)
            
            # If the direct path would intersect the safety zone, create arc waypoints
            if distFromLineToCenter < safetyZoneRadius:
                # Create a tangent path around the sphere
                # Find the tangent point on the sphere closest to the target
                
                # Direction from safety zone center to target
                centerToTarget = normalize([
                    targetPos[0] - safetyZoneCenter[0],
                    targetPos[1] - safetyZoneCenter[1],
                    targetPos[2] - safetyZoneCenter[2]
                ])
                
                # Create intermediate waypoints around the sphere
                # Use 3 waypoints for a smooth arc
                numArcPoints = 3
                
                for i in range(numArcPoints):
                    t = (i + 1) / (numArcPoints + 1)  # Interpolation factor
                    
                    # Spherical interpolation around the safety zone
                    # Start from direction of startPos, end at direction of targetPos
                    startDir = normalize([
                        startPos[0] - safetyZoneCenter[0],
                        startPos[1] - safetyZoneCenter[1],
                        startPos[2] - safetyZoneCenter[2]
                    ])
                    
                    # Interpolate between start and target directions
                    interpDir = [
                        startDir[0] * (1 - t) + centerToTarget[0] * t,
                        startDir[1] * (1 - t) + centerToTarget[1] * t,
                        startDir[2] * (1 - t) + centerToTarget[2] * t
                    ]
                    interpDir = normalize(interpDir)
                    
                    # Place waypoint at safety zone radius distance from center
                    arcPoint = add_vectors(
                        safetyZoneCenter,
                        scale_vector(interpDir, safetyZoneRadius + 5.0)  # +5mm clearance
                    )
                    
                    waypoints.append(arcPoint)
        
        # SEGMENT 3: Approach - move to the final target position
        waypoints.append(targetPos)
        
        # Debug output
        print(f"Generated path with {len(waypoints)} waypoints")
        for i, wp in enumerate(waypoints):
            print(f"  Waypoint {i}: [{wp[0]:.2f}, {wp[1]:.2f}, {wp[2]:.2f}]")
        
        # Create a markups curve node with the waypoints
        # Remove any existing safety path curve
        existingCurve = slicer.util.getFirstNodeByName("PathCurve")
        if existingCurve:
            slicer.mrmlScene.RemoveNode(existingCurve)
        
        # Create new curve node
        curveNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLMarkupsCurveNode', "PathCurve")
        
        # Add the current position as the first control point
        curveNode.AddControlPoint(currentPos[0], currentPos[1], currentPos[2])
        
        # Add all waypoints as control points
        for i, waypoint in enumerate(waypoints):
            curveNode.AddControlPoint(waypoint[0], waypoint[1], waypoint[2])
        
        # Configure the curve appearance
        curveNode.SetCurveTypeToLinear()  # Use linear interpolation between points
        displayNode = curveNode.GetDisplayNode()
        if displayNode:
            displayNode.SetSelectedColor(1.0, 1.0, 1.0)  # White color
            displayNode.SetLineWidth(2.0)
            displayNode.SetTextScale(0.0)  # Hide labels
            displayNode.SetVisibility(False)
        
        return curveNode

    def cranial_make_incision(self, actionParams=None):
        return True, "Doctor, we have made an incision"

    def cranial_drill_hole(self, actionParams=None):
        # Turn off volume rendering visibility for the brain
        brainVolumeNode = slicer.util.getFirstNodeByName("GradientEchoIR_Stripped")
        if brainVolumeNode:
            brainVolumeNode.SetDisplayVisibility(False)

        drillModelNode = slicer.util.getFirstNodeByName("DrillModel")
        if drillModelNode:
            drillModelDisplayNode = drillModelNode.GetDisplayNode()
            if drillModelDisplayNode:
                drillModelDisplayNode.SetVisibility(False)

        catheterModelNode = slicer.util.getFirstNodeByName("CatheterModel")
        if catheterModelNode:
            catheterModelDisplayNode = catheterModelNode.GetDisplayNode()
            if catheterModelDisplayNode:
                catheterModelDisplayNode.SetVisibility(True)

        targetedPointModelNode = slicer.util.getFirstNodeByName("TargetedPointModel")
        if targetedPointModelNode:
            targetedPointModelDisplayNode = targetedPointModelNode.GetDisplayNode()
            if targetedPointModelDisplayNode:
                targetedPointModelDisplayNode.SetVisibility(False)

        self.onNextPhase()
        
        return True, "Doctor, we have successfully drilled the burr hole and are now ready to insert the catheter"

    def start_path_movement(self, pathCurve):
        """Start animated movement along the path curve.
        
        Args:
            pathCurve: vtkMRMLMarkupsCurveNode to follow
        """
        import time
        
        self.currentPathCurve = pathCurve
        self.moving = True
        
        # Calculate total path length
        self.movementTotalDistance = pathCurve.GetCurveLengthWorld()
        
        # Capture starting and target orientations as quaternions
        toolTransformNode = slicer.util.getFirstNodeByName("ToolTransform")
        intendedToolTransformNode = slicer.util.getFirstNodeByName("IntendedToolTransform")
        
        if toolTransformNode and intendedToolTransformNode:
            # Get start orientation
            startMatrix = vtk.vtkMatrix4x4()
            toolTransformNode.GetMatrixTransformToParent(startMatrix)
            self.startOrientation = vtk.vtkQuaternion[float]()
            vtk.vtkMath.Matrix3x3ToQuaternion([
                [startMatrix.GetElement(i, j) for j in range(3)] for i in range(3)
            ], self.startOrientation)
            
            # Get target orientation
            targetMatrix = vtk.vtkMatrix4x4()
            intendedToolTransformNode.GetMatrixTransformToParent(targetMatrix)
            self.targetOrientation = vtk.vtkQuaternion[float]()
            vtk.vtkMath.Matrix3x3ToQuaternion([
                [targetMatrix.GetElement(i, j) for j in range(3)] for i in range(3)
            ], self.targetOrientation)
        
        # Store start time
        self.movementStartTime = time.time()
        
        # Create and start timer (update every 50ms for smooth animation)
        if self.movementTimer is None:
            self.movementTimer = qt.QTimer()
            self.movementTimer.timeout.connect(self.update_path_movement)
        
        self.movementTimer.start(50)  # 50ms = 20 FPS
        
        print(f"Starting movement along path (length: {self.movementTotalDistance:.2f} mm, speed: {self.movementSpeed} mm/s)")

    def update_path_movement(self):
        """Update the tool position along the path curve (called by timer)."""
        import time
        
        if not self.moving or self.currentPathCurve is None:
            return
        
        # Calculate elapsed time and distance traveled
        elapsedTime = time.time() - self.movementStartTime
        distanceTraveled = elapsedTime * self.movementSpeed
        
        # Check if we've reached the end
        if distanceTraveled >= self.movementTotalDistance:
            self.complete_path_movement()
            return
        
        # Calculate progress along path (0.0 to 1.0)
        progress = distanceTraveled / self.movementTotalDistance if self.movementTotalDistance > 0 else 0.0
        
        # Get position along curve at the current distance
        position = [0.0, 0.0, 0.0]
        self.currentPathCurve.GetPositionAlongCurveWorld(position, 0, distanceTraveled)
        
        # Update ToolTransform position and orientation
        toolTransformNode = slicer.util.getFirstNodeByName("ToolTransform")
        if toolTransformNode and self.startOrientation and self.targetOrientation:
            toolMatrix = vtk.vtkMatrix4x4()
            toolTransformNode.GetMatrixTransformToParent(toolMatrix)
            
            # Interpolate orientation using SLERP (Spherical Linear Interpolation)
            interpolatedQuat = vtk.vtkQuaternion[float]()
            interpolatedQuat.SetW(
                self.startOrientation.GetW() * (1.0 - progress) + self.targetOrientation.GetW() * progress
            )
            interpolatedQuat.SetX(
                self.startOrientation.GetX() * (1.0 - progress) + self.targetOrientation.GetX() * progress
            )
            interpolatedQuat.SetY(
                self.startOrientation.GetY() * (1.0 - progress) + self.targetOrientation.GetY() * progress
            )
            interpolatedQuat.SetZ(
                self.startOrientation.GetZ() * (1.0 - progress) + self.targetOrientation.GetZ() * progress
            )
            interpolatedQuat.Normalize()
            
            # Convert quaternion back to rotation matrix
            rotationMatrix = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
            vtk.vtkMath.QuaternionToMatrix3x3(interpolatedQuat, rotationMatrix)
            
            # Update rotation part of transform matrix (3x3 upper-left)
            for i in range(3):
                for j in range(3):
                    toolMatrix.SetElement(i, j, rotationMatrix[i][j])
            
            # Update position elements (translation)
            toolMatrix.SetElement(0, 3, position[0])
            toolMatrix.SetElement(1, 3, position[1])
            toolMatrix.SetElement(2, 3, position[2])
            
            toolTransformNode.SetMatrixTransformToParent(toolMatrix)

    def complete_path_movement(self):
        """Complete the path movement and notify that we're ready."""
        # Stop the timer
        if self.movementTimer:
            self.movementTimer.stop()
        
        # Set the tool to the exact final position (IntendedToolTransform)
        toolTransformNode = slicer.util.getFirstNodeByName("ToolTransform")
        intendedToolTransformNode = slicer.util.getFirstNodeByName("IntendedToolTransform")
        
        if toolTransformNode and intendedToolTransformNode:
            intendedMatrix = vtk.vtkMatrix4x4()
            intendedToolTransformNode.GetMatrixTransformToParent(intendedMatrix)
            toolTransformNode.SetMatrixTransformToParent(intendedMatrix)
        
        # Update state
        self.moving = False
        self.currentPathCurve = None
        
        # Check the drill site for vessel collisions
        self.check_drill_site()
        
        print("Movement complete - arrived at destination")
    # ===========================================================================================

    # ==============================Catheter Placement Functions================================
    def catheter_insert_catheter(self, actionParams):
        # Parse actionParams - it comes as a JSON string
        if isinstance(actionParams, str) and actionParams:
            try:
                actionParams = json.loads(actionParams)
            except json.JSONDecodeError:
                return False, "Doctor, I couldn't understand the distance parameters"
        
        # Now extract the location
        if isinstance(actionParams, dict):
            requestedDistanceString = actionParams["distance"]
        else:
            requestedDistanceString = ""

        # Check if the requested distance is a valid number
        try:
            requestedDistance = float(requestedDistanceString)
        except (ValueError, TypeError):
            return False, "Doctor, I couldn't understand the distance parameters"

        # Start animated catheter movement
        self.start_catheter_movement(requestedDistance, "insert")
        
        return True, f"Doctor, we are inserting the catheter by {requestedDistance:.1f}mm"


    def catheter_retract_catheter(self, actionParams):
        # Parse actionParams - it comes as a JSON string
        if isinstance(actionParams, str) and actionParams:
            try:
                actionParams = json.loads(actionParams)
            except json.JSONDecodeError:
                return False, "Doctor, I couldn't understand the distance parameters"
        
        # Now extract the location
        if isinstance(actionParams, dict):
            requestedDistanceString = actionParams["distance"]
        else:
            requestedDistanceString = ""

        # Check if the requested distance is a valid number
        try:
            requestedDistance = float(requestedDistanceString)
        except (ValueError, TypeError):
            return False, "Doctor, I couldn't understand the distance parameters"

        # Start animated catheter movement
        self.start_catheter_movement(requestedDistance, "retract")
        
        return True, f"Doctor, we are retracting the catheter by {requestedDistance:.1f}mm"

    def catheter_check_position(self):
        """Check if the catheter position is at the selected ventricle position.
        
        Returns:
            tuple: (status, distance_info) where:
                - status: "at_target" if within tolerance, "need_further" if short, "overshot" if past target
                - distance_info: distance in mm (negative if overshot, positive if need to go further)
        """
        print("Checking catheter position")

        # Check if the catheter position is at the selected ventricle position
        toolTransformNode = slicer.util.getFirstNodeByName("ToolTransform")
        intendedToolTransformNode = slicer.util.getFirstNodeByName("IntendedToolTransform")
        
        if not toolTransformNode or not intendedToolTransformNode:
            return "error", 0.0
        
        # Get the catheter current position
        transformMatrix = vtk.vtkMatrix4x4()
        toolTransformNode.GetMatrixTransformToParent(transformMatrix)
        catheterPosition = [
            transformMatrix.GetElement(0, 3),
            transformMatrix.GetElement(1, 3),
            transformMatrix.GetElement(2, 3)
        ]
        
        # Get the starting position (IntendedToolTransform)
        intendedMatrix = vtk.vtkMatrix4x4()
        intendedToolTransformNode.GetMatrixTransformToParent(intendedMatrix)
        startPosition = [
            intendedMatrix.GetElement(0, 3),
            intendedMatrix.GetElement(1, 3),
            intendedMatrix.GetElement(2, 3)
        ]
        
        # Check if selectedVentriclePosition exists
        if not hasattr(self, 'selectedVentriclePosition') or self.selectedVentriclePosition is None:
            print("No selected ventricle position")
            return "error", 0.0
        
        # Calculate distance from current position to target
        distanceToTarget = (
            (catheterPosition[0] - self.selectedVentriclePosition[0]) ** 2 +
            (catheterPosition[1] - self.selectedVentriclePosition[1]) ** 2 +
            (catheterPosition[2] - self.selectedVentriclePosition[2]) ** 2
        ) ** 0.5
        
        # Calculate distance from start to target (total distance needed)
        totalDistanceNeeded = (
            (self.selectedVentriclePosition[0] - startPosition[0]) ** 2 +
            (self.selectedVentriclePosition[1] - startPosition[1]) ** 2 +
            (self.selectedVentriclePosition[2] - startPosition[2]) ** 2
        ) ** 0.5
        
        # Calculate how far we've traveled from start
        distanceTraveled = (
            (catheterPosition[0] - startPosition[0]) ** 2 +
            (catheterPosition[1] - startPosition[1]) ** 2 +
            (catheterPosition[2] - startPosition[2]) ** 2
        ) ** 0.5
        
        # Check if within tolerance (2.5mm)
        tolerance = 2.5
        
        if distanceToTarget <= tolerance:
            print("Catheter is at the target position")
            return "at_target", 0.0
        elif distanceTraveled < totalDistanceNeeded:
            # Need to go further - return positive distance
            print("Catheter is not at the target position, we need to go further")
            return "need_further", totalDistanceNeeded - distanceTraveled
        else:
            # Have overshot - return negative distance
            print("Catheter has overshot the target position")
            return "overshot", -(distanceTraveled - totalDistanceNeeded)


    def catheter_drain(self, actionParams=None):
        return True, "Doctor, we have started draining the ventricles"
    
    def start_catheter_movement(self, distance, movementType):
        """Start animated catheter movement (insert or retract).
        
        Args:
            distance: Distance to move in mm (positive value)
            movementType: "insert" or "retract"
        """
        import time
        
        toolTransformNode = slicer.util.getFirstNodeByName("ToolTransform")
        if not toolTransformNode:
            return
        
        # Get the current transformation matrix
        transformMatrix = vtk.vtkMatrix4x4()
        toolTransformNode.GetMatrixTransformToParent(transformMatrix)
        
        # Extract the Z-axis direction (forward direction) from the rotation matrix
        zAxisDirection = [
            transformMatrix.GetElement(0, 2),
            transformMatrix.GetElement(1, 2),
            transformMatrix.GetElement(2, 2)
        ]
        
        # Get current position
        self.catheterStartPosition = [
            transformMatrix.GetElement(0, 3),
            transformMatrix.GetElement(1, 3),
            transformMatrix.GetElement(2, 3)
        ]
        
        # Set direction based on movement type
        if movementType == "retract":
            # Negative direction for retraction
            self.catheterDirection = [
                -zAxisDirection[0],
                -zAxisDirection[1],
                -zAxisDirection[2]
            ]
        else:  # insert
            self.catheterDirection = zAxisDirection
        
        # Store movement parameters
        self.catheterTotalDistance = abs(distance)
        self.catheterMovementType = movementType
        self.moving = True
        
        # Store start time
        self.catheterStartTime = time.time()
        
        # Create and start timer (update every 50ms for smooth animation)
        if self.catheterTimer is None:
            self.catheterTimer = qt.QTimer()
            self.catheterTimer.timeout.connect(self.update_catheter_movement)
        
        self.catheterTimer.start(50)  # 50ms = 20 FPS
        
        print(f"Starting catheter {movementType} (distance: {distance:.2f} mm, speed: {self.catheterSpeed} mm/s)")
    
    def update_catheter_movement(self):
        """Update the catheter position (called by timer)."""
        import time
        
        if not self.moving:
            return
        
        # Calculate elapsed time and distance traveled
        elapsedTime = time.time() - self.catheterStartTime
        distanceTraveled = elapsedTime * self.catheterSpeed
        
        # Check if we've reached the end
        if distanceTraveled >= self.catheterTotalDistance:
            self.complete_catheter_movement()
            
        
        # Calculate current position
        currentPosition = [
            self.catheterStartPosition[0] + self.catheterDirection[0] * distanceTraveled,
            self.catheterStartPosition[1] + self.catheterDirection[1] * distanceTraveled,
            self.catheterStartPosition[2] + self.catheterDirection[2] * distanceTraveled
        ]
        
        # Update ToolTransform position
        toolTransformNode = slicer.util.getFirstNodeByName("ToolTransform")
        if toolTransformNode:
            toolMatrix = vtk.vtkMatrix4x4()
            toolTransformNode.GetMatrixTransformToParent(toolMatrix)
            
            # Update position elements (translation)
            toolMatrix.SetElement(0, 3, currentPosition[0])
            toolMatrix.SetElement(1, 3, currentPosition[1])
            toolMatrix.SetElement(2, 3, currentPosition[2])
            
            toolTransformNode.SetMatrixTransformToParent(toolMatrix)
    
    def complete_catheter_movement(self):
        """Complete the catheter movement and notify."""
        # Stop the timer
        if self.catheterTimer:
            self.catheterTimer.stop()

        print("Catheter movement complete")
        
        # Set the tool to the exact final position
        toolTransformNode = slicer.util.getFirstNodeByName("ToolTransform")
        if toolTransformNode:
            toolMatrix = vtk.vtkMatrix4x4()
            toolTransformNode.GetMatrixTransformToParent(toolMatrix)
            
            # Calculate final position
            finalPosition = [
                self.catheterStartPosition[0] + self.catheterDirection[0] * self.catheterTotalDistance,
                self.catheterStartPosition[1] + self.catheterDirection[1] * self.catheterTotalDistance,
                self.catheterStartPosition[2] + self.catheterDirection[2] * self.catheterTotalDistance
            ]
            
            # Update position to exact final position
            toolMatrix.SetElement(0, 3, finalPosition[0])
            toolMatrix.SetElement(1, 3, finalPosition[1])
            toolMatrix.SetElement(2, 3, finalPosition[2])
            
            toolTransformNode.SetMatrixTransformToParent(toolMatrix)
        
        # Update state
        self.moving = False

        status, distance = self.catheter_check_position()
        if status == "at_target":
            reportMessage = f"Doctor, we have finished inserting the catheter and it is inside the ventricle. We can proceed with draining."
        elif status == "need_further":
            reportMessage = f"Doctor, we have finished inserting the catheter and it is not inside the ventricle. We need to insert further by {distance:.1f}mm"
        elif status == "overshot":
            reportMessage = f"Doctor, we have finished inserting the catheter and it is not inside the ventricle. We need to retract by {distance:.1f}mm"
        else:
            reportMessage = f"Doctor, something has gone wrong with the catheter movement."
        
        self.websocketHandler.sendContext(reportMessage, False)
    # ===========================================================================================
