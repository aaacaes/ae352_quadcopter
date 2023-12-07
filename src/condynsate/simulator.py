"""
This module provides the Simulator class and all associated classes and 
functions that are used by it.
"""


###############################################################################
#DEPENDENCIES
###############################################################################
import numpy as np
import time
import pybullet
from pybullet_utils import bullet_client as bc
from condynsate.visualizer import Visualizer
from condynsate.animator import Animator
from condynsate.utils import format_path,format_RGB,wxyz_to_xyzw,xyzw_to_wxyz
from condynsate.utils import xyzw_quat_mult, get_rot_from_2_vecs
from condynsate.keyboard import Keys
from matplotlib import colormaps as cmaps


###############################################################################
#URDF OBJECT CLASS
###############################################################################
class URDF_Obj:
    """
    URDF_Obj encapsulates a urdf id, a joint map, and a link map.
    """
    def __init__(self,
                 urdf_id,
                 joint_map,
                 link_map,
                 update_vis,
                 initial_conds):
        """
        Initialize an instance of the URDF_Obj class. This class is used to
        store information relating to a urdf described by a .urdf file.

        Parameters
        ----------
        urdf_id : int
            The unique integer ID of the loaded urdf in the simulation
            engine.
        joint_map : dictionary
            A dictionary that maps all urdf joint names to joint
            indices.
        link_map : dictionary
            A dictionary that maps all urdf link names to joint indices.
        update_vis : bool
            A boolean flag that indicates whether this urdf will be updated
            by the visualizer each time step.
        initial_conds : TODO
            
        Returns
        -------
        None.

        """
        self.urdf_id = urdf_id
        self.joint_map = joint_map
        self.link_map = link_map     
        self.update_vis = update_vis
        self.initial_conds = initial_conds


###############################################################################
#SIMULATOR CLASS
###############################################################################
class Simulator:
    """
    Simulator manages the PyBullet based simulation of dynamic objects and 
    handles automatic visualization
    """
    def __init__(self,
                 visualization=True,
                 animation=True,
                 animation_fr = 10.,
                 gravity=[0., 0., -9.81]):
        """
        Initializes an instance of the Simulator class.

        Parameters
        ----------
        visualization : bool, optional
            A boolean flag that indicates whether the simulation will be 
            visualized in meshcat. The default is True.
        animation : bool, optional
            A boolean flag that indicates whether animated plots are created
            in real time. The default is True.
        animation_fr : float, optional
            The frame rate (frames per second) at which the animated plots are
            updated. The default is 10..
        gravity : array-like, shape (3,) optional
            The gravity vectory in m/s^2. The default is [0., 0., -9.81].

        Returns
        -------
        None.

        """
        # Connect to pybullet
        self.engine = bc.BulletClient(connection_mode=pybullet.DIRECT)
        
        # Configure gravity
        self.set_gravity(gravity)
        
        # Configure physics engine parameters
        self.time = 0.0
        self.dt = 0.01
        self.last_step_time = time.time()
        self.engine.setPhysicsEngineParameter(
            fixedTimeStep=self.dt,
            numSubSteps=4,
            restitutionVelocityThreshold=0.05,
            enableFileCaching=0)
        
        # Keep track of all urdfs loaded to simulator
        self.urdf_objs = []
        
        # Keep track of all the arrows loaded into the visualizer
        self.lin_arr_map = {}
        self.ccw_arr_map = {}
        
        # Create a visualizer
        if visualization:
            self.vis = Visualizer(grid_vis=False,axes_vis=False)
        else:
            self.vis=None
            
        # Create an animator
        if animation:
            self.ani = Animator(fr=animation_fr)
        else:
            self.ani=None
            
        # Start the keyboard listener
        self.keys = Keys()
        
        # Keep track if the simulation is done or not
        self.is_done = False
        
    
    ###########################################################################
    #PHYSICS ENGINE PROPERTY SETTERS
    ###########################################################################
    def set_gravity(self,
                    gravity):
        """
        Sets the acceleration due to gravity vector.

        Parameters
        ----------
        gravity : array-like, shape (3,)
            The acceleration due to gravity vector in m/s^2.

        Returns
        -------
        None.

        """
        # Configure gravity
        self.engine.setGravity(gravity[0],
                               gravity[1],
                               gravity[2])
    
        
    ###########################################################################
    #PHYSICS URDF LOADING
    ###########################################################################
    def load_urdf(self,
                  urdf_path,
                  tex_path='./examples/cmg_vis/check.png',
                  position = [0., 0., 0.],
                  wxyz_quaternion = [1., 0., 0., 0.],
                  roll=None,
                  pitch=None,
                  yaw=None,
                  fixed=False,
                  update_vis=True):
        """
        Loads a URDF to the simulation engine. All joint's
        velocity control is disabled (this allows the joint to move freely),
        angular and linear damping is set to 0 (eliminates air resistance), and 
        joint dampling is set to 0 (eliminates joint friction).

        Parameters
        ----------
        urdf_path : string
            The path to the .urdf file that describes the urdf to be
            loaded into the simulation.
        tex_path : string, optional
            The path pointing towards a texture file. This texture is applied
            only to static .obj objects.
            The default is './examples/cmg_vis/check.png'.
        position : array-like, shape (3,) optional
            The initial position of the urdf. The default is [0., 0., 0.].
        wxyz_quaternion : array-like, shape (4,) optional
            A wxyz quaternion that describes the intial orientation of the
            urdf. When roll, pitch, and yaw all have None type, the
            quaternion is used. If any roll, pitch, or yaw have non None type,
            the quaternion is ignored. The default is [1., 0., 0., 0.].
        roll : float, optional
            The initial roll angle of the urdf. The default is None.
        pitch : float, optional
            The initial pitch angle of the urdf. The default is None.
        yaw : float, optional
            The initial yaw angle of the urdf. The default is None.
        fixed : bool, optional
            A boolean flag that indicates whether the base joint of the
            loaded urdf is fixed. The default is False.
        update_vis : bool, optional
            A boolean flag that indicates whether this urdf will be updated
            by the Visualizer each time step. The default is True.
            
        Returns
        -------
        urdf_obj : URDF_Obj
            A URDF_Obj that describes the urdf that was loaded into
            the simulation.
            
        """
        # Get the properly formatted string of the urdf path
        urdf_path = format_path(urdf_path)
        
        # Get the initial position of the urdf object in world coordinates
        position = np.array(position)
        
        # If no euler angles are specified, use the quaternion to set the
        # initial orientation of the urdf object
        if roll==None and pitch==None and yaw==None: 
            orientation = wxyz_to_xyzw(wxyz_quaternion)
        
        # If any euler angles are specified, use the euler angles to set the
        # initial orientation of the urdf object
        # Any unspecified euler angles are set to 0.0
        else:
            if roll==None:
                roll=0.0
            if pitch==None:
                pitch=0.0
            if yaw==None:
                yaw=0.0
            euler_angles = [roll, pitch,  yaw]
            orientation = self.engine.getQuaternionFromEuler(euler_angles)
        
        # Use implicit cylinder for collision and physics calculation
        # Specifies to the engine to use the inertia from the urdf file
        f1 = self.engine.URDF_USE_IMPLICIT_CYLINDER
        f2 = self.engine.URDF_USE_INERTIA_FROM_FILE
        
        # Load the urdf object
        urdf_id = self.engine.loadURDF(urdf_path,
                                       flags=(f1 | f2),
                                       basePosition=position,
                                       baseOrientation=orientation,
                                       useFixedBase=fixed)
        
        # Get the joint and link maps for the urdf object
        joint_map, link_map = self._make_joint_and_link_maps(urdf_id)
        
        # Record the initial conditions of the URDF
        initial_conds = {'position' : position,
                         'orientation' : orientation,
                         'fixed' : fixed}
        
        # Create urdf_obj and adjust the default state of its joints
        urdf_obj = URDF_Obj(urdf_id,
                            joint_map,
                            link_map,
                            update_vis,
                            initial_conds)
        for joint_name in joint_map:
            
            # Set the joint's friction parameters to model metal to metal
            # friction
            self.set_joint_friction_params(urdf_obj=urdf_obj,
                                           joint_name=joint_name,
                                           lateral_friction=1.0,
                                           spinning_friction=0.0,
                                           rolling_friction=0.0)
            
            # Set the joint's contact parameters to model stiff metal contact
            self.set_joint_contact_params(urdf_obj=urdf_obj,
                                          joint_name=joint_name,
                                          restitution=0.5,
                                          contact_damping=-1.0,
                                          contact_stiffness=-1.0)
            
            # Set the linear and angular damping to 0 (eliminate drag)
            self.set_joint_lin_ang_damp(urdf_obj=urdf_obj,
                                        joint_name=joint_name,
                                        linear_damping=0.,
                                        angular_damping=0.)
            
            # Set damping of joints to 0 (eliminate joint friction)
            self.set_joint_damping(urdf_obj=urdf_obj,
                                   joint_name=joint_name,
                                   damping=0.)

            # If not a base joint
            if joint_map[joint_name]!=-1:
                # Disable velocity control
                self._disable_joint_vel_con(urdf_obj=urdf_obj,
                                            joint_name=joint_name)

                # Enable the force and torque sensor
                self.set_joint_force_sensor(urdf_obj=urdf_obj,
                                            joint_name=joint_name,
                                            enable_sensor=True)

        # Add urdf objects to the visualizer if visualization is occuring
        if isinstance(self.vis, Visualizer):
            self.add_urdf_to_visualizer(urdf_obj=urdf_obj,
                                        tex_path=tex_path)

        # Return the URDF_Obj
        self.urdf_objs.append(urdf_obj)
        return urdf_obj
    
    
    def _make_joint_and_link_maps(self,
                                  urdf_id):
        """
        Creates a joint map and a link map for a urdf.

        Parameters
        ----------
        urdf_id : int
            The unique integer ID of a loaded urdf in the simulation
            engine.

        Returns
        -------
        joint_map : dictionary
            A dictionary that maps all urdf joint names to joint id
        link_map : dictionary
            A dictionary that maps all urdf link names to joint id

        """
        # A dictionary that maps joint names to joint id
        # A dictionary that maps link names to joint id
        joint_map = {}
        link_map = {}

        # Check if the urdf object has a base link
        data = self.engine.getVisualShapeData(urdf_id)
        if data[0][1] == -1:
            joint_map['base'] = -1
            
            base_link_name = self.engine.getBodyInfo(urdf_id)[0]
            base_link_name = base_link_name.decode('UTF-8')
            link_map[base_link_name] = -1
        
        # Go through all joints in the urdf object
        num_joints = self.engine.getNumJoints(urdf_id)
        for joint_id in range(num_joints):

            # Lookup joint info
            joint_info = self.engine.getJointInfo(urdf_id, joint_id)
            joint_name = joint_info[1].decode('UTF-8')
            link_name = joint_info[12].decode('UTF-8')
                
            # Add joint and link data
            joint_map[joint_name] = joint_id
            link_map[link_name] = joint_id
            
        # Return the maps
        return joint_map, link_map
    
    
    def _disable_joint_vel_con(self,
                               urdf_obj,
                               joint_name):
        """
        Disable velocity control mode for a joint. In pybullet, all joints are
        initialized with velocity control mode engaged and a target velocity of
        0. To simulate freely moving joints, velocity control is turned off.

        Parameters
        ----------
        urdf_obj : URDF_Obj
            A URDF_Obj that contains that joint for which velocity control is
            disabled.
        joint_name : string
            The name of the joint whose velocity control is disabled. The
            joint name is specified in the .urdf file.

        Returns
        -------
        None.

        """
        # Gather information from urdf_obj
        urdf_id = urdf_obj.urdf_id
        joint_map = urdf_obj.joint_map
        
        # Set the joint velocity
        if joint_name in joint_map:
            joint_id = [joint_map[joint_name]]
            mode = self.engine.VELOCITY_CONTROL
            self.engine.setJointMotorControlArray(urdf_id,
                                                  joint_id,
                                                  mode,
                                                  forces=[0])
            
            
    ###########################################################################
    #JOINT SETTERS
    ###########################################################################
    def set_joint_force_sensor(self,
                               urdf_obj,
                               joint_name,
                               enable_sensor):
        """
        Enables reaction force, moment, and applied torque to be calculated
        for a joint.

        Parameters
        ----------
        urdf_obj : URDF_Obj
            A URDF_Obj that contains that joint for which the sensor is set.
        joint_name : string
            The name of the joint whose sensor is set.
        enable_sensor : bool
            A boolean flag that indicates whether to enable or disable the
            force sensor.

        Returns
        -------
        None.

        """
        # Gather information from urdf_obj
        urdf_id = urdf_obj.urdf_id
        joint_map = urdf_obj.joint_map
        
        # Set the joint velocity
        if joint_name in joint_map:
            joint_id = joint_map[joint_name]
            self.engine.enableJointForceTorqueSensor(urdf_id,
                                                     joint_id,
                                                     enable_sensor)
    
    
    def set_joint_lin_ang_damp(self,
                               urdf_obj,
                               joint_name,
                               linear_damping=0.,
                               angular_damping=0.):
        """
        Allows user to set the linear and angular damping of a joint. Linear
        and angular damping is a way to model drag. It is typically
        reccomended that the user set these values to 0 for all joints.

        Parameters
        ----------
        urdf_obj : URDF_Obj
            A URDF_Obj that contains that joint whose linear and angular
            damping is being set.
        joint_name : string
            The name of the joint whose linear and angular damping is set. The
            joint name is specified in the .urdf file.
        linear_damping : float, optional
            The value of linear damping to apply. The default is 0..
        angular_damping : float, optional
            The value of angular damping to apply. The default is 0..

        Returns
        -------
        None.

        """
        # Gather information from urdf_obj
        urdf_id = urdf_obj.urdf_id
        joint_map = urdf_obj.joint_map
        
        # Set the joint linear and angular damping
        if joint_name in joint_map:
            joint_id = joint_map[joint_name]
            self.engine.changeDynamics(urdf_id,
                                       joint_id,
                                       linearDamping=linear_damping,
                                       angularDamping=angular_damping)
    
    
    def set_joint_damping(self,
                          urdf_obj,
                          joint_name,
                          damping=0.):
        """
        Sets the damping of a joint in a urdf. The damping of a joint
        defines the energy loss incurred during movement of the joint. It is
        a way to model joint friction.

        Parameters
        ----------
        urdf_obj : URDF_Obj
            A URDF_Obj that contains that joint whose damping is being set.
        joint_name : string
            The name of the joint whose damping is set. The joint name is
            specified in the .urdf file.
        damping : float, optional
            The value of damping to apply. The default is 0..

        Returns
        -------
        None.

        """
        # Gather information from urdf_obj
        urdf_id = urdf_obj.urdf_id
        joint_map = urdf_obj.joint_map
        
        # Set the joint damping
        if joint_name in joint_map:
            joint_id = joint_map[joint_name]
            self.engine.changeDynamics(urdf_id, joint_id, jointDamping=damping)
    
    
    def set_joint_friction_params(self,
                                  urdf_obj,
                                  joint_name,
                                  lateral_friction=0.0,
                                  spinning_friction=0.0,
                                  rolling_friction=0.0):
        """
        Sets a joint's friction parameters. These parameters determine the
        friction characteristics between 2 joints.

        Parameters
        ----------
        urdf_obj : URDF_Obj
            A URDF_Obj that contains that joint whose friction is being set.
        joint_name : string
            The name of the joint whose friction is set. The joint name is
            specified in the .urdf file.
        lateral_friction : float, optional
            The lateral friction applied to the joint. The default is 0.0.
        spinning_friction : float, optional
            The spinning friction applied to the joint. The default is 0.0.
        rolling_friction : float, optional
            The rolling friction applied to the joint. The default is 0.0.

        Returns
        -------
        None.

        """
        # Gather information from urdf_obj
        urdf_id = urdf_obj.urdf_id
        joint_map = urdf_obj.joint_map
        
        # Set the joint friction parameters
        if joint_name in joint_map:
            joint_id = joint_map[joint_name]
            self.engine.changeDynamics(urdf_id,
                                       joint_id,
                                       lateralFriction=lateral_friction, 
                                       spinningFriction=spinning_friction, 
                                       rollingFriction=rolling_friction)
    
    
    def set_joint_contact_params(self,
                                 urdf_obj,
                                 joint_name,
                                 restitution=0.0,
                                 contact_damping=0.0,
                                 contact_stiffness=0.0):
        """
        Sets a joint's contact parameters. These parameters determine the
        energy transfer between two joints in contact.

        Parameters
        ----------
        urdf_obj : URDF_Obj
            A URDF_Obj that contains that joint whose contact params are
            being set.
        joint_name : string
            The name of the joint whose contact params are set.
            The joint name is specified in the .urdf file.
        restitution : float, optional
            The restitution applied to the joint. The default is 0.0.
        contact_damping : float, optional
            The contact damping friction applied to the joint.
            The default is 0.0.
        contact_stiffness : float, optional
            The contact stiffness applied to the joint. The default is 0.0.

        Returns
        -------
        None.

        """
        # Gather information from urdf_obj
        urdf_id = urdf_obj.urdf_id
        joint_map = urdf_obj.joint_map
        
        # Set the joint contact parameters
        if joint_name in joint_map:
            joint_id = joint_map[joint_name]
            self.engine.changeDynamics(urdf_id,
                                       joint_id,
                                       restitution=restitution, 
                                       contactDamping=contact_damping, 
                                       contactStiffness=contact_stiffness)
        
        
    def set_joint_position(self,
                           urdf_obj,
                           joint_name,
                           position=0.,
                           color=False,
                           min_pos=None,
                           max_pos=None):
        """
        Sets the position of a joint of a urdf .

        Parameters
        ----------
        urdf_obj : URDF_Obj
            A URDF_Obj that contains that joint whose position is being set.
        joint_name : string
            The name of the joint whose position is set. The joint name is
            specified in the .urdf file.
        position : float, optional
            The position in rad to be applied to the joint.
            The default is 0..
        color : bool, optional
            A boolean flag that indicates whether to color the joint based on
            its position. The default is False.
        min_pos : float
            The minimum possible position. Used only for coloring. Value is 
            ignored if color is False. The default is None. Must be set to 
            a float value for coloring to be applied.
        max_pos : float
            The maximum possible position. Used only for coloring. Value is 
            ignored if color is False. The default is None. Must be set to 
            a float value for coloring to be applied.

        Returns
        -------
        None.

        """
        # Gather information from urdf_obj
        urdf_id = urdf_obj.urdf_id
        joint_map = urdf_obj.joint_map
        
        # Set the joint velocity
        if joint_name in joint_map:
            joint_id = [joint_map[joint_name]]
            
            # Ensure that we don't try to change a base joint
            if joint_id[0] < 0:
                return
            
            # Set the position
            mode = self.engine.POSITION_CONTROL
            position = [position]
            self.engine.setJointMotorControlArray(urdf_id,
                                                  joint_id,
                                                  mode,
                                                  forces=[1000.],
                                                  targetPositions=position)
           
            # Color the link based on the position
            if color and min_pos!=None and max_pos!=None:
                self.set_color_from_pos(urdf_obj=urdf_obj,
                                        joint_name=joint_name,
                                        min_pos=min_pos, 
                                        max_pos=max_pos)
                
    
    def set_joint_velocity(self,
                          urdf_obj,
                          joint_name,
                          velocity=0.,
                          color=False,
                          min_vel=-100.,
                          max_vel=100.):
        """
        Sets the velocity of a joint of a urdf.

        Parameters
        ----------
        urdf_obj : URDF_Obj
            A URDF_Obj that contains that joint whose velocity is being set.
        joint_name : string
            The name of the joint whose velocity is set. The joint name is
            specified in the .urdf file.
        velocity : float, optional
            The velocity in rad/s to be applied to the joint.
            The default is 0..
        color : bool, optional
            A boolean flag that indicates whether to color the joint based on
            its velocity. The default is False.
        min_vel : float
            The minimum possible velocity. Used only for coloring. Value is 
            ignored if color is False. The default is -100..
        max_vel : float
            The maximum possible velocity. Used only for coloring. Value is 
            ignored if color is False. The default is 100..
            
        Returns
        -------
        None.

        """
        # Gather information from urdf_obj
        urdf_id = urdf_obj.urdf_id
        joint_map = urdf_obj.joint_map
        
        # Set the joint velocity
        if joint_name in joint_map:
            joint_id = [joint_map[joint_name]]
            
            # Ensure that we don't try to change a base joint
            if joint_id[0] < 0:
                return
            
            # Set the velocity
            mode = self.engine.VELOCITY_CONTROL
            velocity = [velocity]
            self.engine.setJointMotorControlArray(urdf_id,
                                                  joint_id,
                                                  mode,
                                                  forces=[1000.],
                                                  targetVelocities=velocity)
            
            # Color the link based on the velocity
            if color:
                self.set_color_from_vel(urdf_obj=urdf_obj,
                                        joint_name=joint_name,
                                        min_vel=min_vel, 
                                        max_vel=max_vel)
    
    
    def set_joint_torque(self,
                         urdf_obj,
                         joint_name,
                         torque=0.,
                         show_arrow=False,
                         arrow_scale=0.1,
                         color=False,
                         min_torque=-1.,
                         max_torque=1.):
        """
        Sets the torque of a joint of a urdf.

        Parameters
        ----------
        urdf_obj : URDF_Obj
            A URDF_Obj that contains that joint whose torque is being set.
        joint_name : string
            The name of the joint whose torque is set. The joint name is
            specified in the .urdf file
        torque : float, optional
            The torque in NM to be applied to the joint. The default is 0..
        show_arrow : bool, optional
            A boolean flag that indicates whether an arrow will be rendered
            on the link to visualize the applied torque. The default is False.
        arrow_scale : float, optional
            The scaling factor that determines the size of the arrow. The
            default is 0.1.
        color : bool, optional
            A boolean flag that indicates whether the child link will be
            colored based on the applied torque. The default is False.
        min_torque : float, optional
            The minimum value of torque that can be applied. Used for link
            coloring. Does nothing if color is not enabled. The default is -1..
        max_torque : float, optional
            The maximum value of torque that can be applied. Used for link
            coloring. Does nothing if color is not enabled. The default is 1..
            
        Returns
        -------
        None.

        """
        # Gather information from urdf_obj
        urdf_id = urdf_obj.urdf_id
        joint_map = urdf_obj.joint_map
        
        # Get the joint_id that defines the joint
        if joint_name in joint_map:
            joint_id = joint_map[joint_name]
        else:
            return
        
        # Ensure that we don't try to change a base joint
        if joint_id < 0:
            return
        
        # If the arrow isn't meant to be visualized, hide it
        vis_exists = isinstance(self.vis, Visualizer)
        arr_exists = joint_name in self.ccw_arr_map
        if (not show_arrow) and vis_exists and arr_exists:
            arrow_name = str(self.ccw_arr_map[joint_name])
            self.vis.set_link_color(urdf_name = "Torque Arrows",
                                    link_name = arrow_name,
                                    stl_path="../shapes/arrow_ccw.stl", 
                                    color = [0, 0, 0],
                                    transparent = True,
                                    e = 0.0)
        
        # Handle torque arrow visualization
        if show_arrow and isinstance(self.vis, Visualizer):
            # Get the orientation, in body coordinates, of the arrow based
            # on direction of torque
            axis = self.get_joint_axis(urdf_obj=urdf_obj,
                                       joint_name=joint_name)
            if torque>=0.:
                arrow_xyzw_in_body = get_rot_from_2_vecs([0,0,1], axis)
            else:
                arrow_xyzw_in_body = get_rot_from_2_vecs([0,0,-1], axis)
                
            # Get the child link of the joint to which torque is applied
            joint_index = list(urdf_obj.link_map.values()).index(joint_id)
            link_name = list(urdf_obj.link_map.keys())[joint_index]
                
            # Get the link state
            pos, body_xyzw_in_world = self.get_link_state(urdf_obj=urdf_obj,
                                                          link_name=link_name)
            body_xyzw_in_world = np.array(body_xyzw_in_world)
            
            # Combine the two rotations
            xyzw_ori = xyzw_quat_mult(arrow_xyzw_in_body, body_xyzw_in_world)
            wxyz_ori = xyzw_to_wxyz(xyzw_ori)
                
            # Get the scale of the arrow based on the magnitude of the torque
            scale = arrow_scale*abs(torque)*np.array([1., 1., 1.])
            scale = scale.tolist()
            
            # If the arrow already exists, only update its position and ori
            if link_name in self.ccw_arr_map:
                arrow_name = str(self.ccw_arr_map[link_name])
                self.vis.set_link_color(urdf_name = "Torque Arrows",
                                        link_name = arrow_name,
                                        stl_path="../shapes/arrow_ccw.stl", 
                                        color = [0, 0, 0],
                                        transparent = False,
                                        opacity = 1.0)
                self.vis.apply_transform(urdf_name="Torque Arrows",
                                         link_name=arrow_name,
                                         scale=scale,
                                         translate=pos,
                                         wxyz_quaternion=wxyz_ori)
            
            # If the arrow is not already created, add it to the visualizer
            else:
                # Add the arrow to the linear arrow map
                self.ccw_arr_map[link_name] = len(self.ccw_arr_map)
                arrow_name = str(self.ccw_arr_map[link_name])
                
                # Add an arrow to the visualizer
                self.vis.add_stl(urdf_name="Torque Arrows",
                                 link_name=arrow_name,
                                 stl_path="../shapes/arrow_ccw.stl",
                                 color = [0, 0, 0],
                                 transparent=False,
                                 opacity = 1.0,
                                 scale=scale,
                                 translate=pos,
                                 wxyz_quaternion=wxyz_ori)
        
        # Set the link color based on applied torque if option is selected.
        if color and isinstance(self.vis, Visualizer):
            self.set_color_from_torque(urdf_obj=urdf_obj,
                                       joint_name=joint_name,
                                       torque=torque,
                                       min_torque=min_torque,
                                       max_torque=max_torque)
        
        
        # Set the joint torque
        if joint_name in joint_map:
            joint_id = [joint_map[joint_name]]
            mode = self.engine.TORQUE_CONTROL
            torque = [torque]
            self.engine.setJointMotorControlArray(urdf_id,
                                                  joint_id,
                                                  mode,
                                                  forces=torque)
            
    ###########################################################################
    #JOINT GETTERS
    ###########################################################################
    def get_joint_state(self,
                        urdf_obj,
                        joint_name):
        """
        Gets the state of a joint (angle and velocity for continuous joints).

        Parameters
        ----------
        urdf_obj : URDF_Obj
            A URDF_Obj whose joint state is being measured.
        joint_name : string
            The name of the joint whose state is measured. The joint name is
            specified in the .urdf file.

        Returns
        -------
        pos : float
            The position value of this joint.
        vel : float
            The velocity value of this joint.
        rxn_force : array-like, shape(3,)
            These are the joint reaction forces. If a torque sensor is enabled
            for this joint it is [Fx, Fy, Fz]. Without torque sensor, it is
            [0., 0., 0.].
        rxn_torque : array-like, shape(3,)
            These are the joint reaction torques. If a torque sensor is enabled
            for this joint it is [Mx, My, Mz]. Without torque sensor, it is
            [0., 0., 0.].
        applied_torque : float
            This is the motor torque applied during the last stepSimulation.
            Note that this only applies in VELOCITY_CONTROL and
            POSITION_CONTROL. If you use TORQUE_CONTROL then the
            applied joint motor torque is exactly what you provide, so there is
            no need to report it separately.
            
        """
        # Get object id and joint id
        urdf_id = urdf_obj.urdf_id
        joint_map = urdf_obj.joint_map
        
        # Get the joint id
        if joint_name in joint_map:
            joint_id = [joint_map[joint_name]]
        else:
            return
        
        # Retrieve the joint states
        states = self.engine.getJointStates(urdf_id, joint_id)
        states = states[0]
        pos = states[0]
        vel = states[1]
        rxn = states[2]
        rxn_force = [rxn[0], rxn[1], rxn[2]]
        rxn_torque = [rxn[3], rxn[4], rxn[5]]
        applied_torque = states[3]
        return pos, vel, rxn_force, rxn_torque, applied_torque
    
    
    def get_joint_axis(self,
                        urdf_obj,
                        joint_name):
        """
        Get the joint axis in local frame.

        Parameters
        ----------
        urdf_obj : URDF_Obj
            A URDF_Obj that contains that joint whose axis is found.
        joint_name : string
            The name of the joint axis is returned.

        Returns
        -------
        axis : array-like, shape(3,)
            The joint axis in local frame.

        """
        # Gather information from urdf_obj
        urdf_id = urdf_obj.urdf_id
        joint_map = urdf_obj.joint_map
        
        # Set the joint velocity
        if joint_name in joint_map:
            joint_id = joint_map[joint_name]
            info = self.engine.getJointInfo(urdf_id,
                                            joint_id)
            axis = info[13]
            axis=np.array(axis).tolist()
            return axis
            
            
    ###########################################################################
    #LINK SETTERS
    ###########################################################################
    def set_link_mass(self,
                      urdf_obj,
                      link_name,
                      mass=0.,
                      color=False,
                      min_mass=None,
                      max_mass=None):
        """
        Sets the mass of a link in a urdf.

        Parameters
        ----------
        urdf_obj : URDF_Obj
            A URDF_Obj that contains that link whose mass is being set.
        link_name : string
            The name of the link whose mass is set. The link name is
            specified in the .urdf file.
        mass : float, optional
            The mass to set in kg. The default is 0..
        color : bool, optional
            A boolean flag that indicates whether to color the joint based on
            its velocity. The default is False.
        min_mass : float
            The minimum possible mass. Used only for coloring. Value is 
            ignored if color is False. The default is None. Must be set to 
            a float value for coloring to be applied.
        max_mass : float
            The maximum possible mass. Used only for coloring. Value is 
            ignored if color is False. The default is None. Must be set to 
            a float value for coloring to be applied.
            
        Returns
        -------
        None.

        """
        # Gather information from urdf_obj
        urdf_id = urdf_obj.urdf_id
        link_map = urdf_obj.link_map
        
        # Set the link mass
        if link_name in link_map:
            joint_id = link_map[link_name]
            self.engine.changeDynamics(urdf_id, joint_id, mass=mass)
            
            # Color the link based on the position
            if color and min_mass!=None and max_mass!=None:
                self.set_color_from_mass(urdf_obj=urdf_obj,
                                         link_name=link_name,
                                         min_mass=min_mass, 
                                         max_mass=max_mass)
                
                    
    ###########################################################################
    #LINK GETTERS
    ###########################################################################
    def get_link_state(self,
                       urdf_obj,
                       link_name):
        """
        Gets the rigid body position and orientation of a link in world
        cooridinates.

        Parameters
        ----------
        urdf_obj : URDF_Obj
            A URDF_Obj that contrains the link whose state is being measured.
        link_name : string
            The name of the link to measure.

        Returns
        -------
        pos_in_world : array-like, shape (3,)
            Cartesian position of center of mass.
        ori_in_world : array-like, shape(4,)
            Cartesian orientation of center of mass, in quaternion [x,y,z,w]

        """
        # Get object id and link map
        urdf_id = urdf_obj.urdf_id
        link_map = urdf_obj.link_map
        
        # Get the link id
        if link_name in link_map:
            link_id = [link_map[link_name]]
        else:
            return
        
        # Retrieve the link states
        link_states = self.engine.getLinkStates(urdf_id, link_id)
        link_states = link_states[0]
        pos_in_world = link_states[0]
        ori_in_world = link_states[1]
        return pos_in_world, ori_in_world
    
    
    def get_link_mass(self,
                      urdf_obj,
                      link_name):
        """
        Gets the current mass of a link.

        Parameters
        ----------
        urdf_obj : URDF_Obj
            A URDF_Obj that contains that link whose mass is measured.
        link_name : string
            The name of the link whose mass is measured. The link name is
            specified in the .urdf file.

        Returns
        -------
        mass : float
            The mass of the link in Kg. If link is not found, returns none.

        """
        # Gather information from urdf_obj
        urdf_id = urdf_obj.urdf_id
        link_map = urdf_obj.link_map
        
        # Ensure the link exists
        if not (link_name in link_map):
           return None
            
        # Get the mass
        link_id = link_map[link_name]
        info = self.engine.getDynamicsInfo(urdf_id,link_id)
        mass = info[0]
        return mass


    ###########################################################################
    #BODY GETTERS
    ###########################################################################
    def get_base_state(self,
                       urdf_obj,
                       body_coords=False):
        """
        Gets the rigid body states (position, orientation, linear velocity, and
        angular velocitiy) of the base of a given urdf. 

        Parameters
        ----------
        urdf_obj : URDF_Obj
            A URDF_Obj whose state is being measured.
        body_coords : bool, optional
            A boolean flag that indicates whether the velocity and angular 
            velocity is given in world coords (False) or body coords (True).
            The default is False.

        Returns
        -------
        pos : array-like, shape (3,)
            The (x,y,z) world coordinates of the base of the urdf.
        rpy : array-like, shape (3,)
            The Euler angles (roll, pitch, yaw) of the base of the urdf
            that define the body's orientation in the world.
        vel : array-like, shape (3,)
            The linear velocity of the base of the urdf in either world 
            coords or body coords.
        ang_vel : array-like, shape (3,)
            The angular velocity of the base of the urdf in either world 
            coords or body coords.

        """
        # Get object id
        urdf_id = urdf_obj.urdf_id
        
        # Retrieve pos, rpy, and vel (in world coordinates) data
        pos, xyzw_ori = self.engine.getBasePositionAndOrientation(urdf_id)
        rpy = self.engine.getEulerFromQuaternion(xyzw_ori)
        vel_world, ang_vel_world = self.engine.getBaseVelocity(urdf_id)
        
        # Format the base state data
        pos = np.array(pos)
        rpy = np.array(rpy)
        vel_world = np.array(vel_world)
        ang_vel_world = np.array(ang_vel_world)
        
        if body_coords:
            # Get the rotation matrix of the body in the world
            R_body_to_world = self.engine.getMatrixFromQuaternion(xyzw_ori)
            R_body_to_world = np.array(R_body_to_world)
            R_body_to_world = np.reshape(R_body_to_world, (3,3))
            
            # Get the body velocities in body coordinates
            R_world_to_body = R_body_to_world.T
            vel_body = R_world_to_body @ vel_world
            ang_vel_body =  R_world_to_body @ ang_vel_world
            
            return pos, rpy, vel_body, ang_vel_body
        
        return pos, rpy, vel_world, ang_vel_world
    
    
    def get_center_of_mass(self,
                           urdf_obj):
        """
        Get the center of mass of a body .

        Parameters
        ----------
        urdf_obj : URDF_Obj
            A URDF_Obj whose center of mass is calculated.

        Returns
        -------
        com : array-like, shape(3,)
            The cartesian coordinates of the center of mass of the body in
            world coordinates.

        """
        # Gather information from urdf_obj
        urdf_id = urdf_obj.urdf_id
        link_map = urdf_obj.link_map
        
        # Go through each link and update body com
        weighted_pos = np.array([0., 0., 0.])
        total_mass = 0.
        for link_name in link_map:
            link_id = link_map[link_name]
            
            # Get the mass of each link
            mass = self.engine.getDynamicsInfo(urdf_id,link_id)[0]
            
            # Get the center of mass of each link
            if link_id==-1:
                pos = self.engine.getBasePositionAndOrientation(urdf_id)[0]
            else:
                pos = self.engine.getLinkState(urdf_id, link_id)[0]
            pos = np.array(pos)
            
            # Update the center of mass parametersd
            weighted_pos = weighted_pos + mass*pos
            total_mass = total_mass + mass
            
        # Calculate the com
        if total_mass > 0.:
            com = weighted_pos / total_mass
        else:
            com = np.array([0., 0., 0.])
        return com
    
    
    ###########################################################################
    #EXTERNAL FORCE AND TORQUE APPLICATION
    ###########################################################################   
    def apply_force_to_link(self,
                            urdf_obj,
                            link_name,
                            force,
                            show_arrow=False,
                            arrow_scale=0.4):
        """
        Applies an external force the to center of a specified link of a urdf.

        Parameters
        ----------
        urdf_obj : URDF_Obj
            A URDF_Obj that contains that link to which the force is applied.
        link_name : string
            The name of the link to which the force is applied.
            The link name is specified in the .urdf file.
        force : array-like, shape (3,)
            The force vector in body coordinates to apply to the link.
        show_arrow : bool, optional
            A boolean flag that indicates whether an arrow will be rendered
            on the link to visualize the applied force. The default is False.
        arrow_scale : float, optional
            The scaling factor that determines the size of the arrow. The
            default is 0.4.
            
        Returns
        -------
        None.

        """
        # Gather information from urdf_obj
        urdf_id = urdf_obj.urdf_id
        link_map = urdf_obj.link_map
        
        # Get the joint_id that defines the link
        if link_name in link_map:
            joint_id = link_map[link_name]
        else:
            return
        
        # Draw the force arrow
        self._apply_force_arrow(urdf_obj=urdf_obj,
                                link_name=link_name,
                                force=force,
                                show_arrow=show_arrow,
                                arrow_scale=arrow_scale)
        
        # Apply the external force
        self.engine.applyExternalForce(urdf_id,
                                       joint_id,
                                       force,
                                       [0., 0., 0.],
                                       flags=self.engine.LINK_FRAME)
                
        
    def apply_force_to_com(self,
                           urdf_obj,
                           force,
                           show_arrow=False,
                           arrow_scale=0.4):
        """
        Applies an external force to the center of mass of the body.

        Parameters
        ----------
        urdf_obj : URDF_Obj
            A URDF_Obj to which the force is applied.
        force : array-like, shape (3,)
            The force vector in world coordinates to apply to the body.
        show_arrow : bool, optional
            A boolean flag that indicates whether an arrow will be rendered
            on the com to visualize the applied force. The default is False.
        arrow_scale : float, optional
            The scaling factor that determines the size of the arrow. The
            default is 0.4.

        Returns
        -------
        None.

        """
        # Gather information from urdf_obj
        urdf_id = urdf_obj.urdf_id
        link_map = urdf_obj.link_map
        
        # Get the highest link in the body tree
        highest_link_id = min(link_map.values())
        
        # Get the center of mass of the body in world cooridnates
        com = self.get_center_of_mass(urdf_obj)
        
        # If the arrow isn't meant to be visualized, hide it
        vis_exists = isinstance(self.vis, Visualizer)
        arr_exists = 'COM' in self.lin_arr_map
        if (not show_arrow) and vis_exists and arr_exists:
            arrow_name = str(self.lin_arr_map['COM'])
            self.vis.set_link_color(urdf_name = "Force Arrows",
                                    link_name = arrow_name,
                                    stl_path="../shapes/arrow_lin.stl", 
                                    color = [0, 0, 0],
                                    transparent = True,
                                    opacity = 0.0)
        
        # Handle force arrow visualization
        if show_arrow and isinstance(self.vis, Visualizer):
            # Get the orientation of the force arrow
            xyzw_ori = get_rot_from_2_vecs([0,0,1], force)
            wxyz_ori = xyzw_to_wxyz(xyzw_ori)
            
            # Get the scale of the arrow based on the magnitude of the force
            scale = arrow_scale*np.linalg.norm(force)*np.array([1., 1., 1.])
            scale=scale.tolist()
            
            # If the arrow already exists, only update its position and ori
            if 'COM' in self.lin_arr_map:
                arrow_name = str(self.lin_arr_map['COM'])
                self.vis.set_link_color(urdf_name = "Force Arrows",
                                        link_name = arrow_name,
                                        stl_path="../shapes/arrow_lin.stl", 
                                        color = [0, 0, 0],
                                        transparent = False,
                                        opacity = 1.0)
                self.vis.apply_transform(urdf_name="Force Arrows",
                                         link_name=arrow_name,
                                         scale=scale,
                                         translate=com,
                                         wxyz_quaternion=wxyz_ori)
            
            # If the arrow is not already created, add it to the visualizer
            else:
                # Add the arrow to the linear arrow map
                self.lin_arr_map['COM'] = len(self.lin_arr_map)
                arrow_name = str(self.lin_arr_map['COM'])
                
                # Add an arrow to the visualizer
                self.vis.add_stl(urdf_name="Force Arrows",
                                 link_name=arrow_name,
                                 stl_path="../shapes/arrow_lin.stl",
                                 color = [0, 0, 0],
                                 transparent=False,
                                 opacity = 1.0,
                                 scale=scale,
                                 translate=com,
                                 wxyz_quaternion=wxyz_ori)
        
        # Apply a force to the highest link at the center of mass of the body
        self.engine.applyExternalForce(urdf_id,
                                       highest_link_id,
                                       force,
                                       com,
                                       flags=self.engine.WORLD_FRAME)
        
        
    def apply_external_torque(self,
                              urdf_obj,
                              torque,
                              show_arrow=False,
                              arrow_scale=0.1):
        """
        Applies an external torque to the center of mass of the body.

        Parameters
        ----------
        urdf_obj : URDF_Obj
            A URDF_Obj to which the torque is applied.
        torque : array-like, shape(3,)
            The torque vector in world coordinates to apply to the body.
        show_arrow : bool, optional
            A boolean flag that indicates whether an arrow will be rendered
            on the com to visualize the applied torque. The default is False.
        arrow_scale : float, optional
            The scaling factor that determines the size of the arrow. The
            default is 0.1.

        Returns
        -------
        None.

        """
        # Gather information from urdf_obj
        urdf_id = urdf_obj.urdf_id
        link_map = urdf_obj.link_map
        
        # Get the highest link in the body tree
        highest_link_id = min(link_map.values())
        
        # Get the center of mass of the body in world cooridnates
        com = self.get_center_of_mass(urdf_obj)
        
        # If the arrow isn't meant to be visualized, hide it
        vis_exists = isinstance(self.vis, Visualizer)
        arr_exists = 'COM' in self.ccw_arr_map
        if (not show_arrow) and vis_exists and arr_exists:
            arrow_name = str(self.lin_arr_map['COM'])
            self.vis.set_link_color(urdf_name = "Torque Arrows",
                                    link_name = arrow_name,
                                    stl_path="../shapes/arrow_ccw.stl", 
                                    color = [0, 0, 0],
                                    transparent = True,
                                    opacity = 0.0)
        
        # Handle force arrow visualization
        if show_arrow and isinstance(self.vis, Visualizer):
            # Get the orientation of the force arrow
            xyzw_ori = get_rot_from_2_vecs([0,0,1], torque)
            wxyz_ori = xyzw_to_wxyz(xyzw_ori)
            
            # Get the scale of the arrow based on the magnitude of the force
            scale = arrow_scale*np.linalg.norm(torque)*np.array([1., 1., 1.])
            scale=scale.tolist()
            
            # If the arrow already exists, only update its position and ori
            if 'COM' in self.ccw_arr_map:
                arrow_name = str(self.ccw_arr_map['COM'])
                self.vis.set_link_color(urdf_name = "Torque Arrows",
                                        link_name = arrow_name,
                                        stl_path="../shapes/arrow_ccw.stl", 
                                        color = [0, 0, 0],
                                        transparent = False,
                                        opacity = 1.0)
                self.vis.apply_transform(urdf_name="Torque Arrows",
                                         link_name=arrow_name,
                                         scale=scale,
                                         translate=com,
                                         wxyz_quaternion=wxyz_ori)
            
            # If the arrow is not already created, add it to the visualizer
            else:
                # Add the arrow to the linear arrow map
                self.ccw_arr_map['COM'] = len(self.ccw_arr_map)
                arrow_name = str(self.ccw_arr_map['COM'])
                
                # Add an arrow to the visualizer
                self.vis.add_stl(urdf_name="Torque Arrows",
                                 link_name=arrow_name,
                                 stl_path="../shapes/arrow_ccw.stl",
                                 color = [0, 0, 0],
                                 transparent=False,
                                 opacity = 1.0,
                                 scale=scale,
                                 translate=com,
                                 wxyz_quaternion=wxyz_ori)
        
        # Apply a force to the highest link at the center of mass of the body
        self.engine.applyExternalTorque(urdf_id,
                                        highest_link_id,
                                        torque,
                                        flags=self.engine.WORLD_FRAME)
        
        
    def _apply_force_arrow(self,
                           urdf_obj,
                           link_name,
                           force,
                           show_arrow,
                           arrow_scale):
        """
        Draws a body coordinate force arrow based on force applied to a link.

        Parameters
        ----------
        urdf_obj : URDF_Obj
            A URDF_Obj that contains that link to which the force is applied.
        link_name : string
            The name of the link to which the force is applied.
            The link name is specified in the .urdf file.
        force : array-like, shape (3,)
            The force vector in body coordinates to apply to the link.
        show_arrow : bool
            A boolean flag that indicates whether an arrow will be rendered
            on the link to visualize the applied force
        arrow_scale : float
            The scaling factor that determines the size of the arrow.

        Returns
        -------
        None.

        """
        # If the arrow isn't meant to be visualized, hide it
        vis_exists = isinstance(self.vis, Visualizer)
        arr_exists = link_name in self.lin_arr_map
        if (not show_arrow) and vis_exists and arr_exists:
            arrow_name = str(self.lin_arr_map[link_name])
            self.vis.set_link_color(urdf_name = "Force Arrows",
                                    link_name = arrow_name,
                                    stl_path="../shapes/arrow_lin.stl", 
                                    color = [0, 0, 0],
                                    transparent = True,
                                    opacity = 0.0)
        
        # Handle force arrow visualization
        if show_arrow and isinstance(self.vis, Visualizer):
            
            # Get the orientation, in body coordinates, of the arrow based
            # on direction of force
            arrow_xyzw_in_body = get_rot_from_2_vecs([0,0,1], force)
            
            # Get the link state
            pos, body_xyzw_in_world = self.get_link_state(urdf_obj=urdf_obj,
                                                          link_name=link_name)
            body_xyzw_in_world = np.array(body_xyzw_in_world)
            
            # Combine the two rotations
            xyzw_ori = xyzw_quat_mult(arrow_xyzw_in_body, body_xyzw_in_world)
            wxyz_ori = xyzw_to_wxyz(xyzw_ori)
            
            # Get the scale of the arrow based on the magnitude of the force
            scale = arrow_scale*np.linalg.norm(force)*np.array([1., 1., 1.])
            scale=scale.tolist()
            
            # If the arrow already exists, only update its position and ori
            if link_name in self.lin_arr_map:
                arrow_name = str(self.lin_arr_map[link_name])
                self.vis.set_link_color(urdf_name = "Force Arrows",
                                        link_name = arrow_name,
                                        stl_path="../shapes/arrow_lin.stl", 
                                        color = [0, 0, 0],
                                        transparent = False,
                                        opacity = 1.0)
                self.vis.apply_transform(urdf_name="Force Arrows",
                                         link_name=arrow_name,
                                         scale=scale,
                                         translate=pos,
                                         wxyz_quaternion=wxyz_ori)
            
            # If the arrow is not already created, add it to the visualizer
            else:
                # Add the arrow to the linear arrow map
                self.lin_arr_map[link_name] = len(self.lin_arr_map)
                arrow_name = str(self.lin_arr_map[link_name])
                
                # Add an arrow to the visualizer
                self.vis.add_stl(urdf_name="Force Arrows",
                                 link_name=arrow_name,
                                 stl_path="../shapes/arrow_lin.stl",
                                 color = [0, 0, 0],
                                 transparent=False,
                                 opacity = 1.0,
                                 scale=scale,
                                 translate=pos,
                                 wxyz_quaternion=wxyz_ori)
                
                
    ###########################################################################
    #URDF VISUALIZATION MANIPULATION
    ###########################################################################
    def add_urdf_to_visualizer(self,
                               urdf_obj,
                               tex_path='./cmg_vis/check.png'):
        """
        Adds urdfs to the Visualizer. URDFs describe systems assembles from
        .stl and .obj links.

        Parameters
        ----------
        vis : Visualizer
            The Visualizer to which the urdf is added.
        urdf_obj : URDF_Obj
            A URDF_Obj that will be added to the Visualizer.
        tex_path : string, optional
            The path pointing towards a texture file. This texture is applied
            to all .obj links in the urdf.

        Returns
        -------
        None.

        """
        # If there is no visualizer, do not attempt to update it
        if not isinstance(self.vis, Visualizer):
            return
        
        # Extract the visual data from the urdf object in the simulator
        paths,names,scales,colors,poss,oris = self._get_urdf_vis_dat(urdf_obj)
        
        # Make the URDF name and format the texture path
        urdf_name = str(urdf_obj.urdf_id)
        tex_path = format_path(tex_path)
        
        # Loop through all the links
        for i in range(len(paths)):
            
            # If the current link is defined by an .obj file
            if paths[i][-4:] == ".obj":
                self.vis.add_obj(urdf_name=urdf_name,
                                 link_name=names[i],
                                 obj_path=paths[i],
                                 tex_path=tex_path,
                                 scale=scales[i],
                                 translate=poss[i],
                                 wxyz_quaternion=oris[i])
                
            # If the current link is defined by an .stl file
            elif paths[i][-4:] == ".stl":
                link_name = names[i]
                rgb = format_RGB(colors[i][0:3],
                                  range_to_255=True)
                opacity = colors[i][3]
                transparent = opacity != 1.0
                self.vis.add_stl(urdf_name=urdf_name,
                                 link_name=link_name,
                                 stl_path=paths[i],
                                 color=rgb,
                                 transparent=transparent,
                                 opacity=opacity,
                                 scale=scales[i],
                                 translate=poss[i],
                                 wxyz_quaternion=oris[i])

    
    def _update_urdf_visual(self,
                            urdf_obj):
        """
        Updates the positions of dynamic links in the Visualizer.

        Parameters
        ----------
        urdf_obj : URDF_Obj, optional
            A URDF_Obj whose links are being updated.

        Returns
        -------
        None.

        """
        # If there is no visualizer, do not attempt to update it
        if not isinstance(self.vis, Visualizer):
            return
        
        # Collect the visual data and urdf name
        paths,names,scales,colors,poss,oris = self._get_urdf_vis_dat(urdf_obj)
        urdf_name = str(urdf_obj.urdf_id)
        
        # Go through all links in urdf object and update their position
        for i in range(len(paths)):
            link_name = names[i]
            self.vis.apply_transform(urdf_name=urdf_name,
                                     link_name=link_name,
                                     scale=scales[i],
                                     translate=poss[i],
                                     wxyz_quaternion=oris[i])
    
    
    def _get_urdf_vis_dat(self,
                          urdf_obj):
        """
        Extracts all relevant visual data from a urdf loaded into the
        simulator.

        Parameters
        ----------
        urdf_obj : URDF_Obj
            A URDF_Obj whose visual data is being extracted.

        Returns
        -------
        paths : list of strings
            A list containing the paths to the files containing urdf or link
            geometries.
        link_names : list of strings
            A list containing the name of all links in the urdf.
        scales : list of lists (3,)
            A list containing the scale data for the urdf or all links
            in the urdf .
        colors : list of lists (4,)
            A list containing the RGBA data for the urdf or all links
            in the urdf.
        positions : list of lists (3,)
            A list containing the position data for the urdf of all
            links in the urdf.
        orientations : list of lists (4,)
            A list containing the wxyz quaternion(s) for the urdf or all
            links in the urdf.

        """
        # Create placeholders for all visual data collected
        paths = []
        link_names = []
        scales = []
        colors = []
        positions = []
        orientations = []
    
        # Determine the urdf id of the object
        urdf_id = urdf_obj.urdf_id
        
        # Get the visual data of the urdf object
        vis_data = self.engine.getVisualShapeData(urdf_id)
        for vis_datum in vis_data:
            path = vis_datum[4].decode('UTF-8')
            path = format_path(path)
            paths.append(path)
            scale = list(vis_datum[3])
            scales.append(scale)
            color = list(vis_datum[7])
            colors.append(color)
            
            # Extract link id
            link_id = vis_datum[1]
            
            # Link id of -1 implies that the current link is the base
            # of a robot
            if link_id == -1:
                base_link_name = self.engine.getBodyInfo(urdf_id)[0]
                base_link_name = base_link_name.decode('UTF-8')
                link_names.append(base_link_name)
                pos_ori = self.engine.getBasePositionAndOrientation(urdf_id)
                position = list(pos_ori[0])
                positions.append(position)
                orientation = list(xyzw_to_wxyz(pos_ori[1]))
                orientations.append(orientation)
                
            # If the link id is not -1, then the current link is not the base.
            # Therefore, position and orientation data is extracted from the
            # joint state and link state
            else:
                # Collect link name
                joint_data = self.engine.getJointInfo(urdf_id, link_id)
                link_name = joint_data[12].decode('UTF-8')
                link_names.append(link_name)
                
                # Extract link positions and orientations
                link_state = self.engine.getLinkState(urdf_id, link_id)
                position = list(link_state[4])
                positions.append(position)
                orientation = list(xyzw_to_wxyz(link_state[5]))
                orientations.append(orientation)
                
        return paths, link_names, scales, colors, positions, orientations
    
    
    ###########################################################################
    #VISUALIZATION COLOR MANIPULATION
    ###########################################################################
    def set_link_color(self,
                          urdf_obj,
                          link_name,
                          color=[91, 155, 213],
                          transparent = False,
                          opacity = 1.0):
        """
        Allows the user to change the color, transparency, and opacity
        of an existing urdf in the simulation. The position and orientation
        are not altered.

        Parameters
        ----------
        urdf_obj : URDF_Obj
            A URDF_Obj that contains that link whose color is being updated.
        link_name : string
            The name of the link whose color is being updated. The link name is
            specified in the .urdf file.
        color : array-like, size (3,), optional
            The 0-255 RGB color of the link.
            The default is [91, 155, 213].
        transparent : boolean, optional
            A boolean that indicates if the link is transparent.
            The default is False.
        opacity : float, optional
            The opacity of the link. Can take float values between 0.0 and 1.0.
            The default is 1.0.

        Returns
        -------
        None.

        """
        # If there is no visualizer, do not attempt to update it
        if not isinstance(self.vis, Visualizer):
            return    
        
        # If the link name doesn't exist, don't attempt to update it
        if not (link_name in urdf_obj.link_map):
            return
    
        # Get name and id data from urdf_obj
        urdf_id = urdf_obj.urdf_id
        urdf_name = str(urdf_id)
        link_id = urdf_obj.link_map[link_name]
        
        # Get current visual data for the requested link
        vis_data = self.engine.getVisualShapeData(urdf_id)
        stl_path = ""
        for vis_datum in vis_data:
            if vis_datum[1] == link_id:
                stl_path = vis_datum[4]
            
        # Format stl path
        stl_path = format_path(stl_path.decode('UTF-8'))
        
        # Ensure color is in proper format
        color = format_RGB(color,
                            range_to_255=False)
        
        # Set the requested color
        self.vis.set_link_color(urdf_name = urdf_name,
                                   link_name = link_name,
                                   stl_path = stl_path, 
                                   color = color,
                                   transparent = transparent,
                                   opacity = opacity)


    def set_color_from_pos(self,
                           urdf_obj,
                           joint_name,
                           min_pos,
                           max_pos):
        """
        Sets the color of the child link of a specified joint based on the 
        position of the joint.

        Parameters
        ----------
        urdf_obj : URDF_Obj
            A URDF_Obj that contains that joint whose position is measured.
        joint_name : string
            The name of the joint whose position is used to set the link color.
            The joint name is specified in the .urdf file.
        min_pos : float
            The minimum possible position of the given joint.
        max_pos : float
            The maximum possible position of the given joint.

        Returns
        -------
        None.

        """
        # Gather information from urdf_obj
        joint_map = urdf_obj.joint_map
    
        # If the joint is invalid, do nothing
        if (joint_name in joint_map):
            joint_id = joint_map[joint_name]
        else:
            return
        
        # If there is no visualizer, do not color
        if not isinstance(self.vis, Visualizer):
            return    
        
        # Get the joint position
        pos,_,_,_,_ = self.get_joint_state(urdf_obj=urdf_obj,
                                           joint_name=joint_name)
        
        # Calculate the position saturation and get the associated color
        sat = np.clip((pos - min_pos) / (max_pos - min_pos), 0.0, 1.0)
        col = cmaps['coolwarm'](round(255*sat))[0:3]
        col = format_RGB(col,
                         range_to_255=True)
        
        # Get the child link of the joint from which pos is measured
        joint_index = list(urdf_obj.link_map.values()).index(joint_id)
        link_name = list(urdf_obj.link_map.keys())[joint_index]
        
        # Set link color
        self.set_link_color(urdf_obj=urdf_obj,
                            link_name=link_name,
                            color=col)
        
        
    def set_color_from_vel(self,
                           urdf_obj,
                           joint_name,
                           min_vel=-100.,
                           max_vel=100.):
        """
        Sets the color of the child link of a specified joint based on the 
        velocity of the joint.

        Parameters
        ----------
        urdf_obj : URDF_Obj
            A URDF_Obj that contains that joint whose velocity is measured.
        joint_name : string
            The name of the joint whose velocity is used to set the link color.
            The joint name is specified in the .urdf file.
        min_vel : float, optional
            The minimum possible velocity of the given joint. The default is
            -100.. Unless otherwise set, PyBullet does not allow joint
            velocities to exceed a magnitude of 100.
        max_vel : float, optional
            The maximum possible velocity of the given joint. The default is
            100.. Unless otherwise set, PyBullet does not allow joint
            velocities to exceed a magnitude of 100.

        Returns
        -------
        None.

        """
        # Gather information from urdf_obj
        joint_map = urdf_obj.joint_map
    
        # If the joint is invalid, do nothing
        if (joint_name in joint_map):
            joint_id = joint_map[joint_name]
        else:
            return
        
        # If there is no visualizer, do not color
        if not isinstance(self.vis, Visualizer):
            return    
        
        # Get the joint velocity
        _,vel,_,_,_ = self.get_joint_state(urdf_obj=urdf_obj,
                                           joint_name=joint_name)
        
        # Calculate the velocity saturation and get the associated color
        sat = np.clip((vel - min_vel) / (max_vel - min_vel), 0.0, 1.0)
        col = cmaps['coolwarm'](round(255*sat))[0:3]
        col = format_RGB(col,
                         range_to_255=True)
        
        # Get the child link of the joint from which vel is measured
        joint_index = list(urdf_obj.link_map.values()).index(joint_id)
        link_name = list(urdf_obj.link_map.keys())[joint_index]
        
        # Set link color
        self.set_link_color(urdf_obj=urdf_obj,
                            link_name=link_name,
                            color=col)
    
    
    def set_color_from_torque(self,
                              urdf_obj,
                              joint_name,
                              torque,
                              min_torque=-1.,
                              max_torque=1.):
        """
        Sets the color of the child link of a specified joint based on the 
        torque applied to the joint.

        Parameters
        ----------
        urdf_obj : URDF_Obj
            A URDF_Obj that contains that joint whose torque is measured.
        joint_name : string
            The name of the joint whose torque is used to set the link color.
            The joint name is specified in the .urdf file.
        torque : float
            The torque applied to the joint.
        min_torque : float, optional
            The minimum possible torque to apply to the joint. The default is
            -1..
        max_torque : float, optional
            The maximum possible torque to apply to the joint. The default is
            
            1..

        Returns
        -------
        None.

        """
        # Gather information from urdf_obj
        joint_map = urdf_obj.joint_map
    
        # If the joint is invalid, do nothing
        if (joint_name in joint_map):
            joint_id = joint_map[joint_name]
        else:
            return
        
        # If there is no visualizer, do not color
        if not isinstance(self.vis, Visualizer):
            return    
        
        # Calculate the torque saturation and get the associated color
        sat = (torque - min_torque) / (max_torque - min_torque)
        sat = np.clip(sat, 0.0, 1.0)
        col = cmaps['coolwarm'](round(255*sat))[0:3]
        col = format_RGB(col,
                         range_to_255=True)
        
        # Get the child link of the joint from which torque is measured
        joint_index = list(urdf_obj.link_map.values()).index(joint_id)
        link_name = list(urdf_obj.link_map.keys())[joint_index]
        
        # Set link color
        self.set_link_color(urdf_obj=urdf_obj,
                            link_name=link_name,
                            color=col)
        
        
    def set_color_from_mass(self,
                            urdf_obj,
                            link_name,
                            min_mass,
                            max_mass):
        """
        Sets the color of a link based on its mass.

        Parameters
        ----------
        urdf_obj : URDF_Obj
            A URDF_Obj that contains that joint whose torque is measured.
        link_name : string
            The name of the link whose mass is used to set the link color.
            The link name is specified in the .urdf file.
        min_mass : float, optional
            The minimum possible mass of the link.
        max_mass : float, optional
            The maximum possible mass of the link.

        Returns
        -------
        None.

        """
        # Gather information from urdf_obj
        link_map = urdf_obj.link_map
    
        # If the link is invalid, do nothing
        if not (link_name in link_map):
            return
        
        # If there is no visualizer, do not color
        if not isinstance(self.vis, Visualizer):
            return    
        
        # Get the mass
        mass = self.get_link_mass(urdf_obj=urdf_obj,
                                  link_name=link_name)
        
        # Calculate the mass saturation and get the associated color
        sat = (mass - min_mass) / (max_mass - min_mass)
        sat = np.clip(sat, 0.0, 1.0)
        col = cmaps['binary'](round(255*sat))[0:3]
        col = format_RGB(col,
                         range_to_255=True)
        
        # Set link color
        self.set_link_color(urdf_obj=urdf_obj,
                            link_name=link_name,
                            color=col)
        
        
    ###########################################################################
    #VISUALIZATION SCENE MANIPULATION
    ###########################################################################
    def transform_camera(self,
                         scale = [1., 1., 1.],
                         translate = [0., 0., 0.],
                         wxyz_quaternion = [1., 0., 0., 0.],
                         roll=None,
                         pitch=None,
                         yaw=None):
        """
        Transforms the position, orientation, and scale of the Visualizer's
        camera.

        Parameters
        ----------
        scale : array-like, size (3,), optional
            The scaling of the camera view about the camera point along the
            three axes. The default is [1., 1., 1.].
        translate : array-like, size (3,), optional
            The translation of the camera point along the three axes.
            The default is [0., 0., 0.].
        wxyz_quaternion : array-like, shape (4,) optional
            A wxyz quaternion that describes the intial orientation of camera
            about the camera point. When roll, pitch, and yaw all have None
            type, the quaternion is used. If any roll, pitch, or yaw have non
            None type, the quaternion is ignored.
            The default is [1., 0., 0., 0.].
        roll : float, optional
            The roll of the camera about the camera point.
            The default is None.
        pitch : float, optional
            The pitch of the camera about the camera point.
            The default is None.
        yaw : float, optional
            The yaw of the camera about the camera point.
            The default is None.

        Returns
        -------
        None.

        """
        # If there is no visualizer, do not attempt to update it
        if not isinstance(self.vis, Visualizer):
            return
        
        # Apply the camera transform
        else:
            self.vis.transform_camera(scale = scale,
                                      translate = translate,
                                      wxyz_quaternion = wxyz_quaternion,
                                      roll=roll,
                                      pitch=pitch,
                                      yaw=yaw)
            
            
    def set_background(self,
                       top_color = None,
                       bot_color = None):
        """
        Set the top and bottom colors of the background of the Visualizer.
    
        Parameters
        ----------
        top_color : array-like, shape (3,), optional
            The 0-255 color to apply to the top of the background.
            The default is None. If top_color is set to None, top_color
            is not altered.
        bot_color : array-like, shape (3,), optional
            The 0-255 color to apply to the bottom of the background.
            The default is None. If bot_color is set to None, bot_color
            is not altered.
    
        Returns
        -------
        None.
    
        """
        # If there is no visualizer, do not attempt to update it
        if not isinstance(self.vis, Visualizer):
            return
        
        # Apply the background colors
        else:
            self.vis.set_background(top_color = top_color,
                                    bot_color = bot_color)
     
        
    def set_spotlight(self,
                      on = False,
                      intensity = 1.0,
                      distance = 100.):
        """
        Sets the properties of the spotlight in the Visualizer.

        Parameters
        ----------
        on : bool, optional
            A boolean flag that indicates whether the spotlight is on.
            The default is False.
        intensity : float (0. to 20.), optional
            The brightness of the spotlight. The default is 1.0.
        distance : float (0. to 100.), optional
            The distance from the origin of the spotlight. The default is 100..

        Returns
        -------
        None.

        """
        # If there is no visualizer, do not attempt to update it
        if not isinstance(self.vis, Visualizer):
            return
        
        # Apply the background colors
        else:
            self.vis.set_spotlight(on = on,
                                   intensity = intensity,
                                   distance = distance)
    
    
    def set_posx_pt_light(self,
                          on = False,
                          intensity = 1.0,
                          distance = 100.):
        """
        Sets the properties of the point light on the positive x axis
        in the Visualizer.

        Parameters
        ----------
        on : bool, optional
            A boolean flag that indicates whether the light is on.
            The default is False.
        intensity : float (0. to 20.), optional
            The brightness of the light. The default is 1.0.
        distance : float (0. to 100.), optional
            The distance from the origin of the light. The default is 100..

        Returns
        -------
        None.

        """
        # If there is no visualizer, do not attempt to update it
        if not isinstance(self.vis, Visualizer):
            return
        
        # Apply the background colors
        else:
            self.vis.set_posx_pt_light(on = on,
                                       intensity = intensity,
                                       distance = distance)
            
            
    def set_negx_pt_light(self,
                          on = False,
                          intensity = 1.0,
                          distance = 100.):
        """
        Sets the properties of the point light on the negative x axis
        in the Visualizer.

        Parameters
        ----------
        on : bool, optional
            A boolean flag that indicates whether the light is on.
            The default is False.
        intensity : float (0. to 20.), optional
            The brightness of the light. The default is 1.0.
        distance : float (0. to 100.), optional
            The distance from the origin of the light. The default is 100..

        Returns
        -------
        None.

        """
        # If there is no visualizer, do not attempt to update it
        if not isinstance(self.vis, Visualizer):
            return
        
        # Apply the background colors
        else:
            self.vis.set_negx_pt_light(on = on,
                                       intensity = intensity,
                                       distance = distance)
            
            
    def set_ambient_light(self,
                          on = False,
                          intensity = 1.0):
        """
        Sets the properties of the ambient light of the Visualizer.

        Parameters
        ----------
        on : bool, optional
            A boolean flag that indicates whether the light is on.
            The default is False.
        intensity : float (0. to 20.), optional
            The brightness of the light. The default is 1.0.

        Returns
        -------
        None.

        """
        # If there is no visualizer, do not attempt to update it
        if not isinstance(self.vis, Visualizer):
            return
        
        # Apply the background colors
        else:
            self.vis.set_ambient_light(on = on,
                                       intensity = intensity)
            
            
    def set_fill_light(self,
                          on = False,
                          intensity = 1.0):
        """
        Sets the properties of the fill light in the Visualizer.

        Parameters
        ----------
        on : bool, optional
            A boolean flag that indicates whether the light is on.
            The default is False.
        intensity : float (0. to 20.), optional
            The brightness of the light. The default is 1.0.

        Returns
        -------
        None.

        """
        # If there is no visualizer, do not attempt to update it
        if not isinstance(self.vis, Visualizer):
            return
        
        # Apply the background colors
        else:
            self.vis.set_fill_light(on = on,
                                       intensity = intensity)
        
        
    ###########################################################################
    #ANIMATOR MANIPULATION
    ###########################################################################
    def add_plot_to_animator(self,
                             title=None,
                             x_label=None,
                             y_label=None,
                             color=None,
                             line_width=None,
                             line_style=None,
                             tail=None,
                             x_lim=[None, None],
                             y_lim=[None, None]):
        """
        Adds a plot to the Animator. This function needs to be called to 
        define a plot before that plot's data can be set or updated

        Parameters
        ----------
        title : string, optional
            The title of the plot. Will be written above the plot when
            rendered. The default is None.
        x_label : string, optional
            The label to apply to the x axis. We be written under the plot when
            rendered. The default is None.
        y_label : string, optional
            The label to apply to the y axis. We be written to the left of the
            plot when rendered. The default is None.
        color : matplotlib color string, optional
            The color of the plot lines. The default is None.
        line_width : float, optional
            The weight of the line that is plotted. The default is None.
            When set to None, defaults to 1.0.
        line_style : matplotlib line style string, optional
            The style of the line that is plotted. The default is None. When 
            set the None, defaults to solid.
        tail : int, optional
            The number of points that are used to draw the line. Only the most 
            recent data points are kept. A value of None will plot all points
            in the plot data. The default is None.
        x_lim : [float, float], optional
            The limits to apply to the x axis of the plots. A value of None
            will apply automatically updating limits to that bound of the axis.
            The default is [None, None].
        y_lim : [float, float], optional
            The limits to apply to the y axis of the plots. A value of None
            will apply automatically updating limits to that bound of the axis.
            The default is [None, None].

        Returns
        -------
        plot_index : int
            A unique integer identifier that allows future plot interation.

        """
        # If there is no animator, do not attempt to add a plot to it
        if not isinstance(self.ani, Animator):
            return
        
        # Add the plot data to the plot
        plot_index = self.ani.add_plot(title=title,
                                       x_label=x_label,
                                       y_label=y_label,
                                       color=color,
                                       line_width=line_width,
                                       line_style=line_style,
                                       tail=tail,
                                       x_lim=x_lim,
                                       y_lim=y_lim)
        
        # Return the plot index
        return plot_index
        
        
    def set_plot_data(self,
                      plot_index,
                      x,
                      y):
        """
        Sets the data to be plotted for an individual plot. 

        Parameters
        ----------
        plot_index : int
            The plot's unique identifier. Provided by add_plot_to_animator().
        x : array-like, shape(n,)
            An array of the x data.
        y : array-like, shape(n,)
            An array of the y data.

        Returns
        -------
        None.

        """
        # If there is no animator, do not attempt to update it
        if not isinstance(self.ani, Animator):
            return
        
        # Update the plot
        self.ani.set_plot_data(plot_index=plot_index,
                               x=x,
                               y=y)
        
        
    def erase_all_plot_data(self):
        # If there is no animator, do not attempt to update it
        if not isinstance(self.ani, Animator):
            return
        
        for plot_index in range(self.ani.n_plots):
            self.ani.set_plot_data(plot_index=plot_index,
                                   x=[],
                                   y=[])
        
        
    def open_animator_gui(self):
        """
        Opens the Animator GUI with the specified plots. After the Animator
        is open, no more plots can be added; however, the plot data can still
        be set.

        Returns
        -------
        None.

        """
        # Open the animator figure window if it exists
        if isinstance(self.ani, Animator):
            self.ani.create_figure()
        
        
    ###########################################################################
    #SIMULATION EXECUTION
    ###########################################################################
    def is_pressed(self,
                   key):
        """
        Wrapper for the keyboard.Keys.is_pressed() function.
        Returns a boolean flag to indicate whether a desired key is pressed.
        The key may be alpha numeric or some special keys.

        Parameters
        ----------
        key : string
            The key to be detected. May be alpha numeric ("a", "A", "1", "!",
            "`", etc.) or some special keys. The special keys are as follows:
            "space", "enter", "backspace", "tab", "shift", "alt", "tab",
            "ctrl", and "esc". The following modifiers can also be used:
            "shift+", "alt+", and "ctrl+". Modifiers are added with the
            following format: "shift+a", "ctrl+a", "alt+a", "shift+ctrl+alt+a",
            etc. If "esc" is pressed, the keyboard listener will automatically
            stop and cannot be restarted.

        Returns
        -------
        bool
            A boolean flag to indicate whether the desired key is pressed.

        """
        return self.keys.is_pressed(key)
        
        
    def await_keypress(self,
                       key="enter"):
        """
        Suspends the simulation until a specified keystroke is recieved.
        When an Animator GUI is open, this function must be called to
        keep the GUI responsive. If a GUI is not present, this function is
        optional. 

        Parameters
        ----------
        key : string, optional
            The key string identifier. The default is "enter".

        Returns
        -------
        None.

        """
        print("PRESS "+key.upper()+" TO CONTINUE."+
              "\nPRESS ESC TO QUIT."+
              "\nPRESS TAB TO RESET SIMULATION.")
        while not self.is_pressed("enter"):
            # Ensure so the GUI remains interactive if simulation is suspended
            if isinstance(self.ani, Animator):
                self.ani.flush_events()
        
        # Note that the simulation is started
        print("CONTINUING...")
        self.is_started = True
      
        
    def reset(self,
              update_vis,
              update_ani):
        # Note that the simulation is resetting to the user
        print("RESETTING...")
        
        # Note the simulation is no longer done and reset the time
        self.is_done = False
        self.time = 0.
        self.last_step_time = time.time()
        
        # Reset each urdf
        for urdf_obj in self.urdf_objs:
            
            # Reset the base position and orientation of all urdfs
            i = urdf_obj.urdf_id
            p = urdf_obj.initial_conds['position']
            o = urdf_obj.initial_conds['orientation']
            self.engine.resetBasePositionAndOrientation(bodyUniqueId=i,
                                                        posObj=p,
                                                        ornObj=o)
            
            # Reset each joint
            for joint_name in urdf_obj.joint_map.keys():
                
                # Ensure we aren't setting a base joint
                joint_id = urdf_obj.joint_map[joint_name]
                if joint_id!=-1:
                    
                    # Reset joint state to 0
                    self.engine.resetJointState(bodyUniqueId=urdf_obj.urdf_id,
                                                jointIndex=joint_id,
                                                targetValue=0.0,
                                                targetVelocity=0.0)
                    
                    # Set the joint torque to 0
                    self.set_joint_torque(urdf_obj,
                                          joint_name,
                                          torque=0.,
                                          show_arrow=False,
                                          color=False,)
        
        #TODO Reset the plots
        self.erase_all_plot_data()
        
        
        # Update the visualizer if it exists
        if update_vis and isinstance(self.vis, Visualizer):
            for urdf_obj in self.urdf_objs:
                if urdf_obj.update_vis:
                    self._update_urdf_visual(urdf_obj)
        
        # Update the animator if it exists
        if update_ani and isinstance(self.ani, Animator):
            self.ani.step()
    
        # Wait one half second to prevent multiple resets
        time.sleep(0.5)
        
        
    def step(self,
             real_time=True,
             update_vis=True,
             update_ani=True):
        """
        Takes a single step of the simulation. In this step, the physics
        engine, the Visualizer (3D visualization of urdfs), and the Animator
        (2D animation of plots) are all updated.

        Parameters
        ----------
        real_time : bool, optional
            A boolean flag that indicates whether or not the step is taken in
            real time. If True, step() is suspended until the time since the
            last step is equal to 0.01 seconds (the fixed time step of the
            physics engine). If False, step() is run as quickly as possible.
            The default is True.
        update_vis : bool, optional
            A boolean flag that indicates whether the Visualizer is updated.
            The default is True.
        update_ani : bool, optional
            A boolean flag that indicates whether the Animator is updated.
            The default is True.

        Returns
        -------
        None.

        """
        # Note that the simulation is started
        self.is_started = True
        
        # Calculate suspend time if running in real time
        if real_time:
            time_since_last_step = time.time() - self.last_step_time
            time_to_wait = self.dt - time_since_last_step
            if time_to_wait > 0:
                time.sleep(time_to_wait)
            
        # Step the physics engine
        self.engine.stepSimulation()
        
        # Update the time
        self.last_step_time = time.time()
        self.time = self.time + self.dt
        
        # Update the visualizer if it exists
        if update_vis and isinstance(self.vis, Visualizer):
            for urdf_obj in self.urdf_objs:
                if urdf_obj.update_vis:
                    self._update_urdf_visual(urdf_obj)
                    
        # Update the animator if it exists
        if update_ani and isinstance(self.ani, Animator):
            self.ani.step()
        
        # Collect keyboard IO for simulation reset
        if self.is_pressed("tab"):
            self.reset(update_vis = update_vis,
                       update_ani = update_ani)
        
        # Collect keyboard IO for termination
        if self.is_pressed("esc"):
            self.is_done = True
            