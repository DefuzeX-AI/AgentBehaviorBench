#include "SDroneWidget.h"

#include "SubWidget/SCameraView.h"
#include "SubWidget/SCommandHistoryPanel.h"
#include "SubWidget/SEquipmentInfoPanel.h"
#include "SubWidget/SEquipmentMiniMap.h"
#include "ue5project/Interaction/UserInterface/Equipment/EquipmentWidgetController.h"

void SDroneWidget::Construct(const FArguments& InArgs)
{	
	const TWeakObjectPtr<UTextureRenderTarget2D> FrontRenderTarget = InArgs._FrontRenderTarget;
	const TWeakObjectPtr<UTextureRenderTarget2D> TopdownRenderTarget = InArgs._TopdownRenderTarget;
	
	ChildSlot
	[
		SNew(SOverlay)
		+ SOverlay::Slot()
		.Padding(20.f, 20.f, 0.f, 0.f)
		.HAlign(HAlign_Left)
		.VAlign(VAlign_Top)
		[
			SNew(SVerticalBox)
			+ SVerticalBox::Slot()
			.Padding(0.f, 20.f, 0.f, 0.f)
			[
				SAssignNew(FrontCameraView, SCameraView)
				.RenderTarget(FrontRenderTarget)
			]
			+ SVerticalBox::Slot()
			.Padding(0.f, 20.f, 0.f, 0.f)
			[
				SAssignNew(TopdownCameraView, SCameraView)
				.RenderTarget(TopdownRenderTarget)
			]
		]
		+ SOverlay::Slot()
		.Padding(0.f, 20.f, 20.f, 0.f)
		.HAlign(HAlign_Right)
		.VAlign(VAlign_Top)
		[
			SNew(SVerticalBox)
			+ SVerticalBox::Slot()
			.AutoHeight()
			[
				SAssignNew(InfoPanel, SEquipmentInfoPanel)
			]
			+ SVerticalBox::Slot()
			.Padding(0.f, 20.f, 0.f, 0.f)
			[
				SAssignNew(CommandHistory, SCommandHistoryPanel)
			]
		]
	];

	FEquipmentWidgetController::Get()->OnEquipmentTransformUpdateDelegate.BindRaw(this, &SDroneWidget::OnEquipmentTransformUpdated);
	FEquipmentWidgetController::Get()->OnTrajectoryPointAddedDelegate.BindRaw(this, &SDroneWidget::OnEquipmentMoved);
	FEquipmentWidgetController::Get()->OnCommandAddedDelegate.BindRaw(this, &SDroneWidget::OnCommandAdd);
}

void SDroneWidget::OnEquipmentTransformUpdated(const FTransform& InTransform) const
{
	if (InfoPanel.IsValid())
	{
		InfoPanel->UpdateTransform(InTransform);
	}
}

void SDroneWidget::OnEquipmentMoved(const FVector2D& InPoint) const
{
	if (MiniMap.IsValid())
	{
		MiniMap->AddTrajectoryPoint(InPoint);
	}
}

void SDroneWidget::OnCommandAdd(const FString& InType, const FString& InContent) const
{
	if (CommandHistory.IsValid())
	{
		CommandHistory->AddCommand(InType, InContent);
	}
}

