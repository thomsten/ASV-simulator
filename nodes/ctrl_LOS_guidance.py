#!/usr/bin/env python
import numpy as np
import rospy
import geometry_msgs.msg
import nav_msgs.msg
from visualization_msgs.msg import Marker

from matplotlib.patches import Circle

from utils import Controller

class LOSGuidanceROS(object):
    """A ROS wrapper for LOSGuidance()."""
    def __init__(self, rate, R2=20**2, u_d=3.0, switch_criterion='circle'):
        self.controller = LOSGuidance(R2, u_d, switch_criterion)
        self.rate = rate
        self.wp   = self.controller.wp
        self.nwp  = 0
        self.cwp  = 0

        self._cmd_publisher   = rospy.Publisher("cmd_vel", geometry_msgs.msg.Twist)
        self._odom_subscriber = rospy.Subscriber("odom", nav_msgs.msg.Odometry, self._odom_callback)
        self._wps_publisher   = rospy.Publisher("waypoints", Marker)


        self.odom = nav_msgs.msg.Odometry()
        self.cmd  = geometry_msgs.msg.Twist()
        self.cmd.linear.x = u_d

        self._first_draw = True

    def set_waypoints(self, wps):
        self.wp = wps
        self.controller.wp = np.copy(wps)
        self.controller.nWP = len(wps)
        self.controller.wp_initialized = True
        self.nwp = len(wps)

    def _visualize_waypoints(self, switched):
        if not switched and not self._first_draw:
            return

        if self._first_draw:
            for wp in range(0, self.nwp):
                mk = Marker()
                mk.header.seq += 1
                mk.header.frame_id = "map"
                mk.header.stamp = rospy.Time.now()

                mk.ns = "waypoints"
                mk.id = wp
                mk.type = Marker.CYLINDER
                D = np.sqrt(self.controller.R2)
                mk.scale.x = D
                mk.scale.y = D
                mk.scale.z = 2. # height [m]
                mk.action = Marker.ADD

                mk.pose = geometry_msgs.msg.Pose()
                mk.pose.position.x = self.wp[wp,0]
                mk.pose.position.y = self.wp[wp,1]
                mk.pose.orientation.w = 1

                mk.lifetime = rospy.Duration()
                mk.color.a = .3
                mk.color.r = 0.
                mk.color.g = 0.
                mk.color.b = 0.

                if wp == self.cwp:
                    mk.color.g = 1.
                else:
                    mk.color.r = 1.

                self._wps_publisher.publish(mk)
        else:
            for wp in [self.cwp-1, self.cwp]:
                mk = Marker()
                mk.header.seq += 1
                mk.header.frame_id = "map"
                mk.header.stamp = rospy.Time.now()

                mk.ns = "waypoints"
                mk.id = wp
                mk.type = Marker.CYLINDER
                D = np.sqrt(self.controller.R2)*2
                mk.scale.x = D
                mk.scale.y = D
                mk.scale.z = 2. # height [m]
                mk.action = Marker.ADD

                mk.pose = geometry_msgs.msg.Pose()
                mk.pose.position.x = self.wp[wp,0]
                mk.pose.position.y = self.wp[wp,1]
                mk.pose.orientation.w = 1

                mk.lifetime = rospy.Duration()
                mk.color.a = .3
                mk.color.r = 0.
                mk.color.g = 0.
                mk.color.b = 0.

                if wp == self.cwp:
                    mk.color.g = 1.
                else:
                    mk.color.r = 1.



                self._wps_publisher.publish(mk)

        self._first_draw = True

    def _odom_callback(self, data):
        self.odom = data

    def _update(self):

        u_d, psi_d, switched = self.controller.update(self.odom.pose.pose.position.x,
                                                      self.odom.pose.pose.position.y)
        if switched:
            print "Switched!"
            self.cwp += 1

        # Publish cmd_vel
        self.cmd.linear.x = u_d
        self.cmd.angular.y = psi_d
        self.cmd.angular.z = 0.0

        self._cmd_publisher.publish(self.cmd)

        self._visualize_waypoints(switched)

    def run_controller(self):
        r = rospy.Rate(1/self.rate)

        while not rospy.is_shutdown():
            self._update()
            r.sleep()

class LOSGuidance(Controller):
    """This class implements the classic LOS guidance scheme."""
    def __init__(self, R2=20**2, u_d = 3.0, switch_criterion='circle'):
        self.R2 = R2 # Radii of acceptance (squared)
        self.R  = np.sqrt(R2)
        self.de = 20 # Lookahead distance

        self.cWP = 0 # Current waypoint
        self.wp = None
        self.nWP = 0
        self.wp_initialized = False

        if switch_criterion == 'circle':
            self.switching_criterion = self.circle_of_acceptance
        elif switch_criterion == 'progress':
            self.switching_criterion = self.progress_along_path

        self.Xp = 0.0
        self.u_d = u_d

    def __str__(self):
        return """Radii: %f\nLookahead distance: %f\nCurrent Waypoint: %d"""%(self.R, self.de, self.cWP)

    def circle_of_acceptance(self, x, y):
        return \
            (x - self.wp[self.cWP][0])**2 + \
            (y - self.wp[self.cWP][1])**2 < self.R2

    def progress_along_path(self, x, y):
        return \
            np.abs((self.wp[self.cWP][0] - x)*np.cos(self.Xp) + \
                   (self.wp[self.cWP][1] - y)*np.sin(self.Xp)) < self.R

    def update(self, x, y):
        if not self.wp_initialized:
            print "Error. No waypoints!"
            return 0,0,False

        #print self.wp[self.cWP,:], str(self)
        switched = False

        if self.switching_criterion(x, y):
            while self.switching_criterion(x,y):
                if self.cWP < self.nWP - 1:
                # There are still waypoints left
                    print "Waypoint %d: (%.2f, %.2f) reached!" % (self.cWP,
                                                                  self.wp[self.cWP][0],
                                                                  self.wp[self.cWP][1])
                    # print "Next waypoint: (%.2f, %.2f)" % (self.wp[self.cWP+1][0],
                    #                                        self.wp[self.cWP+1][1])
                    self.Xp = np.arctan2(self.wp[self.cWP + 1][1] - self.wp[self.cWP][1],
                                         self.wp[self.cWP + 1][0] - self.wp[self.cWP][0])
                    self.cWP += 1
                    switched = True
                else:
                    # Last waypoint reached

                    if self.R2 < 50000:
                        print "Waypoint %d: (%.2f, %.2f) reached!" % (self.cWP,
                                                                      self.wp[self.cWP][0],
                                                                      self.wp[self.cWP][1])
                        print "Last Waypoint reached!"
                        self.R2 = np.Inf
                    return 0,0,False


        xk = self.wp[self.cWP][0]
        yk = self.wp[self.cWP][1]

        # Eq. (10.10), [Fossen, 2011]
        e  = -(x - xk)*np.sin(self.Xp) + (y - yk)*np.cos(self.Xp)

        Xr = np.arctan2( -e, self.de)
        psi_d = self.Xp + Xr


        return self.u_d, psi_d, switched

    def visualize(self, fig, axarr, t, n):
        axarr[0].plot(self.wp[:,0], self.wp[:,1], 'k--')
        axarr[0].plot(self.wp[self.cWP+1,0], self.wp[self.cWP+1,1], 'rx', ms=10)

    def draw(self, axes, N, wpcolor='y', ecolor='k'):

        axes.plot(self.wp[:,0], self.wp[:,1], wpcolor+'--')
        return
        #ii = 0
        for wp in self.wp[1:]:
            circle = Circle((wp[0], wp[1]), 10, facecolor=wpcolor, alpha=0.3, edgecolor='k')
            axes.add_patch(circle)
            #axes.annotate(str(ii), xy=(wp[0], wp[1]), xytext=(wp[0]+5, wp[1]-5))
            #ii += 1

if __name__ == "__main__":
    rospy.init_node("LOS_Guidance_controller")
    print "yolo"
    guide = LOSGuidanceROS(.2)

    wps = np.array([[50,50],[120,70],[200,150],[100,0]])
    guide.set_waypoints( wps)

    guide.run_controller()
