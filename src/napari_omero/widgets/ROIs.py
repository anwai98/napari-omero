import warnings

import napari.viewer
from magicgui.widgets import Container, PushButton, create_widget
from napari.layers import Image, Labels
from napari.utils.notifications import show_info

from napari_omero.plugins.loaders import load_rois
from napari_omero.plugins.omero import save_rois
from napari_omero.utils import lookup_obj
from napari_omero.widgets.gateway import QGateWay
from omero.cli import ProxyStringType


def omero_roi_manager() -> Container:
    """A widget to manage ROIs between napari and OMERO.

    This widget handles both loading ROI from OMERO, as well as saving
    napari annotations to OMERO as ROI.
    """
    omero_image_combobox = create_widget(label="OMERO Image", annotation=Image)
    load_button = PushButton(text="Load Annotations from OMERO")
    save_button = PushButton(text="Upload Annotations to OMERO")
    collection_mbutton = PushButton(text="Fetch Masks from OMERO Collection")
    collection_ibutton = PushButton(text="Fetch Images from OMERO Collection")

    @load_button.clicked.connect
    def _load_rois_from_omero() -> None:
        viewer = napari.viewer.current_viewer()
        image_layer = omero_image_combobox.value

        if not image_layer or "omero" not in image_layer.metadata:
            show_info("No OMERO metadata found in selected layer.")
            return

        gateway = QGateWay()
        layer_name = image_layer.name
        img_id = int(layer_name.split(":")[0])

        image_wrapper = gateway.conn.getObject("Image", img_id)
        points_coords, points_meta, _ = load_rois(
            gateway.conn, image_wrapper, load_points=True
        )[0]
        shapes_coords, shapes_meta, _ = load_rois(
            gateway.conn, image_wrapper, load_points=False
        )[0]

        if points_meta is None and shapes_meta is None:
            show_info(f"No ROIs or points found for OMERO image id {img_id}.")
            return
        if shapes_meta:
            viewer.add_shapes(shapes_coords, **shapes_meta)
        if points_meta:
            viewer.add_points(points_coords, **points_meta)

    @save_button.clicked.connect
    def _save_rois_to_omero() -> None:
        omero_image = omero_image_combobox.value
        # check if 'omero' field is in metadata
        if not omero_image or "omero" not in omero_image.metadata:
            warnings.warn("No OMERO metadata found in selected layer.", stacklevel=2)
            return

        # assert that layer is 4D if it is a labels layer
        if isinstance(omero_image, Labels) and omero_image.ndim != 4:
            raise ValueError(
                "Labels layer must be 4D (time, z, y, x) to be uploaded to OMERO."
            )

        gateway = QGateWay()
        image_id = omero_image.metadata["omero"]["@id"]

        image_wrapper = lookup_obj(
            gateway.conn, ProxyStringType("Image")(f"Image:{image_id}")
        )

        viewer = napari.viewer.current_viewer()
        save_rois(viewer=viewer, image=image_wrapper)

        trg = image_wrapper.getName()
        show_info(f"All annotation layers uploaded to OMERO image id {image_id}: {trg}")

    def _fetch_stuff_from_collection(stype):
        image_layer = omero_image_combobox.value

        if not image_layer or "omero" not in image_layer.metadata:
            show_info("No OMERO metadata found in selected layer.")
            return

        gateway = QGateWay()
        layer_name = image_layer.name
        img_id = int(layer_name.split(":")[0])

        # Let's time how long it takes to do all the fetching
        import time
        start = time.time()
        from biohack_utils.omero_annotation import fetch_omero_labels_in_napari

        if stype == "images":
            more_images = fetch_omero_labels_in_napari(
                gateway.conn, img_id, label_node_type="Intensities"
            )
        elif stype == "labels":
            more_images = fetch_omero_labels_in_napari(gateway.conn, img_id)
        else:
            raise NotImplementedError

        end = time.time()
        print(f"It took ca. {round(end - start)}s to fetch the mask labels.")

        return more_images

    @collection_mbutton.clicked.connect
    def _fetch_mask_labels_from_collection() -> None:
        """Fetches the mask from a collection.
        """
        viewer = napari.viewer.current_viewer()
        labels = _fetch_stuff_from_collection("labels")
        for _k, _v in labels.items():
            viewer.add_labels(_v, name=_k)

    @collection_ibutton.clicked.connect
    def _fetch_additional_images_from_collection() -> None:
        """Fetches additional images from the same collection.
        """
        viewer = napari.viewer.current_viewer()
        more_images = _fetch_stuff_from_collection("images")

        if not more_images:
            print("Oopsie, ich bin kaputt. No additional images found in the collection.")
            return

        for _k, _v in more_images.items():
            viewer.add_image(_v, name=_k)

    container = Container(
        widgets=[omero_image_combobox, load_button, save_button, collection_mbutton, collection_ibutton]
    )
    return container
