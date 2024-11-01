import jax
import jax.numpy as jnp
from jaxgl.maths import signed_line_distance
from jaxgl.renderer import clear_screen, make_renderer
from jaxgl.shaders import fragment_shader_circle, fragment_shader_quad
from matplotlib import pyplot as plt

from jax2d.engine import PhysicsEngine, create_empty_sim
from jax2d.maths import rmat
from jax2d.scene import add_circle_to_scene, add_rectangle_to_scene
from jax2d.sim_state import StaticSimParams, SimParams


def mask_shader(shader_fn):
    @jax.jit
    def masked_shader(position, current_frag, unit_position, uniform):
        inner_uniforms = uniform[:-1]
        mask = uniform[-1]

        inner_fragment = shader_fn(position, current_frag, unit_position, inner_uniforms)
        return jax.lax.select(mask, inner_fragment, current_frag)

    return masked_shader


def make_render_pixels(
    static_sim_params,
):
    screen_dim = (500, 500)

    ppud = 100
    patch_size = 512
    screen_padding = patch_size
    full_screen_size = (
        screen_dim[0] + 2 * screen_padding,
        screen_dim[1] + 2 * screen_padding,
    )

    def _world_space_to_pixel_space(x):
        return x * ppud + screen_padding

    cleared_screen = clear_screen(full_screen_size, jnp.zeros(3))

    circle_renderer = make_renderer(
        full_screen_size, mask_shader(fragment_shader_circle), (patch_size, patch_size), batched=True
    )
    quad_renderer = make_renderer(
        full_screen_size, mask_shader(fragment_shader_quad), (patch_size, patch_size), batched=True
    )

    @jax.jit
    def render_pixels(state):
        pixels = cleared_screen

        # Rectangles
        rect_positions_pixel_space = _world_space_to_pixel_space(state.polygon.position)
        rectangle_rmats = jax.vmap(rmat)(state.polygon.rotation)
        rectangle_rmats = jnp.repeat(
            rectangle_rmats[:, None, :, :], repeats=static_sim_params.max_polygon_vertices, axis=1
        )
        rectangle_vertices_pixel_space = _world_space_to_pixel_space(
            state.polygon.position[:, None, :] + jax.vmap(jax.vmap(jnp.matmul))(rectangle_rmats, state.polygon.vertices)
        )
        rect_patch_positions = (rect_positions_pixel_space - (patch_size / 2)).astype(jnp.int32)
        rect_patch_positions = jnp.maximum(rect_patch_positions, 0)

        rect_colours = jnp.ones((static_sim_params.num_polygons, 3)) * 128.0
        rect_uniforms = (rectangle_vertices_pixel_space, rect_colours, state.polygon.active)

        pixels = quad_renderer(pixels, rect_patch_positions, rect_uniforms)

        # Circles
        circle_positions_pixel_space = _world_space_to_pixel_space(state.circle.position)
        circle_radii_pixel_space = state.circle.radius * ppud
        circle_patch_positions = (circle_positions_pixel_space - (patch_size / 2)).astype(jnp.int32)
        circle_patch_positions = jnp.maximum(circle_patch_positions, 0)

        circle_colours = jnp.ones((static_sim_params.num_circles, 3)) * 255.0

        circle_uniforms = (
            circle_positions_pixel_space,
            circle_radii_pixel_space,
            circle_colours,
            state.circle.active,
        )

        pixels = circle_renderer(pixels, circle_patch_positions, circle_uniforms)

        # Crop out the sides
        return pixels[screen_padding:-screen_padding, screen_padding:-screen_padding]

    return render_pixels


def main():
    # Create engine with default parameters
    static_sim_params = StaticSimParams()
    sim_params = SimParams()
    engine = PhysicsEngine(static_sim_params)

    # Create scene
    sim_state = create_empty_sim(static_sim_params)
    sim_state = add_circle_to_scene(sim_state, jnp.ones(2) * 2, 1)
    sim_state = add_rectangle_to_scene(sim_state, jnp.ones(2), jnp.array([0.5, 1.0]), static_sim_params)
    sim_state = add_rectangle_to_scene(sim_state, jnp.ones(2) * 2, jnp.array([1.5, 1.0]), static_sim_params)
    sim_state = add_rectangle_to_scene(sim_state, jnp.ones(2) * 3, jnp.array([2.5, 1.0]), static_sim_params)

    # Renderer
    renderer = make_render_pixels(static_sim_params)

    # Step scene
    step_fn = jax.jit(engine.step)
    for i in range(1000):
        print(i)
        actions = jnp.zeros(static_sim_params.num_joints + static_sim_params.num_thrusters)
        sim_state, _ = step_fn(sim_state, sim_params, actions)

    # Render
    pixels = renderer(sim_state)
    plt.imshow(pixels.astype(jnp.uint8).transpose((1, 0, 2))[::-1])
    plt.show()


if __name__ == "__main__":
    debug = False

    if debug:
        print("JIT disabled")
        with jax.disable_jit():
            main()
    else:
        main()
