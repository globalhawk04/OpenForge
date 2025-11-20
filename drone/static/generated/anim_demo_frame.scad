
    use </home/j/Desktop/viz_it/drone/cad/library.scad>;
    $fn=50;
    union() {
        frame_body(77.0, 2.5);
        translate([27.2195, 27.2195, 0]) motor_mount(6.6, 2);
        translate([- 27.2195, 27.2195, 0]) motor_mount(6.6, 2);
        translate([- 27.2195, - 27.2195, 0]) motor_mount(6.6, 2);
        translate([27.2195, - 27.2195, 0]) motor_mount(6.6, 2);
        translate([0,0,2.5]) fc_mount(25.5);
    }
    