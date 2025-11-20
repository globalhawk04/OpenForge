
    use </home/j/Desktop/viz_it/drone/cad/library.scad>;

    $fn=50;
    
    // Parameters
    WHEELBASE = 77.0;
    MOTOR_MOUNT = 6.6;
    FC_MOUNT = 25.5;
    
    // Generate
    union() {
        frame_body(WHEELBASE, 2.5);
        
        // Motor Mounts
        translate([WHEELBASE/2 * 0.707, WHEELBASE/2 * 0.707, 0]) motor_mount(MOTOR_MOUNT, 2);
        translate([-WHEELBASE/2 * 0.707, WHEELBASE/2 * 0.707, 0]) motor_mount(MOTOR_MOUNT, 2);
        translate([-WHEELBASE/2 * 0.707, -WHEELBASE/2 * 0.707, 0]) motor_mount(MOTOR_MOUNT, 2);
        translate([WHEELBASE/2 * 0.707, -WHEELBASE/2 * 0.707, 0]) motor_mount(MOTOR_MOUNT, 2);
        
        // FC Stack
        translate([0,0,2.5]) fc_mount(FC_MOUNT);
    }
    