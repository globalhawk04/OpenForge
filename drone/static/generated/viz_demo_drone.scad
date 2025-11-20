
    use </home/j/Desktop/viz_it/drone/cad/library.scad>;
    $fn=50;
    WHEELBASE = 77.0;
    MOTOR_MOUNT = 6.6;
    FC_MOUNT = 25.5;
    
    union() {
        frame_body(WHEELBASE, 2.5);
        translate([WHEELBASE/2 * 0.707, WHEELBASE/2 * 0.707, 0]) motor_mount(MOTOR_MOUNT, 2);
        translate([-WHEELBASE/2 * 0.707, WHEELBASE/2 * 0.707, 0]) motor_mount(MOTOR_MOUNT, 2);
        translate([-WHEELBASE/2 * 0.707, -WHEELBASE/2 * 0.707, 0]) motor_mount(MOTOR_MOUNT, 2);
        translate([WHEELBASE/2 * 0.707, -WHEELBASE/2 * 0.707, 0]) motor_mount(MOTOR_MOUNT, 2);
        translate([0,0,2.5]) fc_mount(FC_MOUNT);
    }
    